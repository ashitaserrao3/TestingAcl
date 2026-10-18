import copy
import datetime as dt
import hashlib
import html
import io
import os
import re
import zipfile

import openpyxl
import streamlit as st
import streamlit_authenticator as stauth

import allcargo
import store
from tariffapp import database_path, db, queries, sync
from tariffapp.etl import parsers
from tariffapp.linker import STATUS_CHECK, STATUS_NO_RATE, STATUS_NO_TARIFF, TariffEngine

st.set_page_config(page_title="Flight Schedule", page_icon="✈️", layout="wide")

# =====================================================
# AUTHENTICATION
# Users + cookie key live in Streamlit Secrets, never in the repo.
#   Community Cloud : App settings -> Secrets
#   Local run       : .streamlit/secrets.toml (git-ignored)
# =====================================================


def _to_dict(obj):
    """st.secrets is read-only; the authenticator needs a normal dict."""
    if hasattr(obj, "items"):
        return {k: _to_dict(v) for k, v in obj.items()}
    return copy.deepcopy(obj)


if "credentials" not in st.secrets or "cookie" not in st.secrets:
    st.error(
        "Login settings are missing. Add the [credentials] and [cookie] sections "
        "to Streamlit Secrets (see secrets.toml.example)."
    )
    st.stop()

credentials = _to_dict(st.secrets["credentials"])
cookie = _to_dict(st.secrets["cookie"])

authenticator = stauth.Authenticate(
    credentials,
    cookie["name"],
    cookie["key"],
    float(cookie.get("expiry_days", 30)),
    auto_hash=False,  # passwords in secrets are already bcrypt hashes
)

# =====================================================
# LOGIN SCREEN
# =====================================================

if not st.session_state.get("authentication_status"):
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        try:
            authenticator.login(
                fields={"Form name": "Sign in", "Username": "Username",
                        "Password": "Password", "Login": "Sign in"},
            )
        except Exception as e:
            st.error(e)
        if st.session_state.get("authentication_status") is False:
            st.error("Username or password is incorrect", icon="🔒")

    if st.session_state.get("authentication_status"):
        st.rerun()  # signed in (or remembered) -> show the flight schedule
    st.stop()

# =====================================================
# SIGNED IN: FLIGHT SCHEDULE
# Everyone who signs in sees the schedule. Only ADMIN_USER gets the sidebar
# to upload the schedule and tariff rates it is built from.
# =====================================================

ADMIN_USER = "ashita"

# Colours taken from the workbook's own formatting
NAVY, BLUE, GREEN_DARK = "#1F4E78", "#2E74B5", "#375623"
BAND, INPUT_YELLOW, STRIPE, GREY_TEXT, MSG_BROWN = "#DCE6F1", "#FFF2CC", "#F2F2F2", "#595959", "#833C0C"
STATUS_FILL = {"ACTIVE": "#C6E0B4", "NO SERVICE": "#F8CBAD", "SAME CITY": "#FFF2CC"}
CHECK_AMBER = "#FFE699"
LOWEST_RED = "#FFC7CE"  # Excel's "light red fill"

SHEET_CSS = f"""
<style>
.xl {{ font-family: Aptos Narrow, "Arial Narrow", Calibri, Arial, sans-serif; color: #000; }}
.xl-title {{ background: {NAVY}; color: #fff; font-weight: 700; font-size: 24px; text-align: center;
             padding: 10px 0; letter-spacing: .08em; }}
.xl-rates {{ color: {GREY_TEXT}; font-size: 12px; text-align: right; margin: 2px 0 6px; }}
.xl-band {{ display: grid; grid-template-columns: 4fr 2fr 2fr 3fr; background: {BAND}; }}
.xl-band > div {{ padding: 4px 10px 6px; min-width: 0; }}
.xl-band .k {{ font-size: 12px; font-weight: 700; }}
.xl-band .v {{ color: {NAVY}; font-weight: 700; font-size: 21px; line-height: 1.25; }}
.xl-band .route {{ font-size: 17px; overflow-wrap: anywhere; }}
.xl-band .st {{ color: #000; font-size: 18px; }}
.xl-msg {{ color: {MSG_BROWN}; font-weight: 700; text-align: center; padding: 10px 0 4px; font-size: 15px; }}
.xl-wrap {{ overflow-x: auto; margin-top: 10px; }}
.xl-table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
.xl-table th {{ background: {BLUE}; color: #fff; font-weight: 700; text-align: center; padding: 5px 8px;
                border: 1px solid #fff; white-space: nowrap; }}
.xl-table th.cpkg {{ background: {GREEN_DARK}; }}
.xl-table td {{ padding: 5px 8px; border-bottom: 1px solid #E7E7E7; white-space: nowrap; }}
.xl-table tbody tr:nth-child(even) td {{ background: {STRIPE}; }}
.xl-table td.c {{ text-align: center; }}
.xl-table td.cpkg {{ text-align: center; color: {GREEN_DARK}; font-weight: 700; font-size: 15px; }}
.xl-table tr.lowest td {{ background: {LOWEST_RED} !important; }}
.xl-table td.check {{ background: {CHECK_AMBER} !important; }}
.xl-table td.muted {{ color: #808080; }}
.xl-table sup {{ color: #9C5700; font-size: 10px; font-weight: 400; }}
.xl-note {{ color: {GREY_TEXT}; font-size: 11px; margin-top: 10px; }}
.xl-special {{ color: #5B2C83; font-weight: 700; text-align: center; padding: 8px 0 0; font-size: 14px; }}
.sp {{ background: #E4D7F5; color: #5B2C83; font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
       letter-spacing: .04em; }}
</style>
"""

WIDGET_CSS = f"""
<style>
/* Origin / Destination drop-downs styled like the workbook's yellow input cells */
.st-key-origin [role="group"], .st-key-dest [role="group"],
.st-key-origin div[data-baseweb="select"] > div, .st-key-dest div[data-baseweb="select"] > div {{
  background: {INPUT_YELLOW}; border-radius: 0;
}}
.st-key-origin input, .st-key-dest input {{ color: {NAVY}; font-weight: 700; font-size: 16px; }}
.xl-label {{ font-weight: 700; text-align: right; font-size: 15px; }}
.xl-name {{ color: {GREY_TEXT}; font-size: 15px; }}
</style>
"""

TITLE = '<div class="xl xl-title">✈&nbsp; FLIGHT &nbsp;SCHEDULE</div>'


def dmy(v):
    if not v:
        return ""
    if isinstance(v, str):
        v = dt.date.fromisoformat(v[:10])
    return v.strftime("%d-%b-%y")


def esc(v):
    return html.escape("" if v is None else str(v))


def num(v):
    if v is None:
        return ""
    return f"{v:g}" if float(v) == int(v) else f"{v:.2f}"


def github_store():
    """The GitHub branch the uploads are kept on, or None when [github] isn't in Secrets."""
    cfg = st.secrets.get("github", {})
    if not cfg.get("token"):
        return None
    return store.GitHubStore(cfg["token"], cfg.get("repo", "ashitaserrao3/TestingAcl"), cfg.get("branch", "data"))


@st.cache_resource(show_spinner="Loading the saved schedule and tariff files…")
def restore_uploads():
    """Once per app start: bring back the files Ashita last uploaded. Returns an error message or None."""
    gh = github_store()
    if gh is None:
        return None
    try:
        gh.pull(sync.data_dir())
    except Exception as e:  # noqa: BLE001 - shown to Ashita; the app still runs on what it has
        return f"Couldn't load the saved files from GitHub: {e}"
    return None


@st.cache_resource(show_spinner="Loading the latest data…", max_entries=1)
def build_database(signature):
    """A fresh database from exactly the files in the data folder, shared by every visitor and rebuilt
    whenever the files change - so the schedule always shows the latest upload and nothing older."""
    name = hashlib.sha1(repr(signature).encode()).hexdigest()[:12]
    path = os.path.join(os.path.dirname(database_path()), f"tariff-{name}.sqlite")
    tmp = path + ".tmp"
    for p in (tmp, tmp + "-wal", tmp + "-shm"):
        if os.path.exists(p):
            os.remove(p)
    c = db.connect(tmp)
    try:
        db.init_schema(c)
        result = sync.sync_data_folder(c)
        c.execute("PRAGMA journal_mode = DELETE")  # one self-contained file, safe to rename
    finally:
        c.close()
    os.replace(tmp, path)
    folder = os.path.dirname(path)
    for f in os.listdir(folder):  # databases built from older uploads
        if f.startswith("tariff-") and not f.startswith(os.path.basename(path)):
            os.remove(os.path.join(folder, f))
    return path, result


def data_signature():
    """Changes whenever any uploaded file is added, replaced or removed."""
    files = store.local_files(sync.data_dir()) if os.path.isdir(sync.data_dir()) else {}
    return tuple(sorted((rel, os.path.getsize(p), int(os.path.getmtime(p))) for rel, p in files.items()))


def newest(folder, extensions):
    paths = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(extensions)] if os.path.isdir(folder) else []
    return max(paths, key=lambda p: (os.path.getmtime(p), p), default=None)


@st.cache_resource(show_spinner="Loading the Allcargo and special rates…", max_entries=1)
def load_extras(signature):
    """(Allcargo quotation, Akasa special rates, errors) from the data folder."""
    quote = special = None
    errors = []
    for sub, ext, reader in (("allcargo", sync.XLSX, allcargo.read_quote), ("special", (".pdf",), allcargo.read_special)):
        path = newest(os.path.join(sync.data_dir(), sub), ext)
        if not path:
            continue
        try:
            data = reader(path)
            data["file"] = os.path.basename(path)
            if sub == "allcargo":
                quote = data
            else:
                special = data
        except Exception as e:  # noqa: BLE001 - shown to Ashita
            errors.append(f"{os.path.basename(path)}: {e}")
    return quote, special, errors


def clean_name(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", os.path.basename(name)).strip() or "upload"


def expand(uploads):
    """[(name, bytes)] for the uploaded files, with .zip files unpacked."""
    out = []
    for f in uploads:
        if f.name.lower().endswith(".zip"):
            with zipfile.ZipFile(f) as z:
                for info in z.infolist():
                    base = os.path.basename(info.filename)
                    if info.is_dir() or not base or base.startswith((".", "~$")) or "__MACOSX" in info.filename:
                        continue
                    out.append((clean_name(base), z.read(info)))
        else:
            out.append((clean_name(f.name), f.getvalue()))
    return out


def replace_files(folder, items, old_extensions):
    """Remove the folder's previous files of these types, then write the new ones."""
    if items and os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.lower().endswith(old_extensions):
                os.remove(os.path.join(folder, name))
    os.makedirs(folder, exist_ok=True)
    for name, data in items:
        with open(os.path.join(folder, name), "wb") as out:
            out.write(data)


def save_schedule(items):
    """DGCA PDFs replace all the previous PDFs; a workbook replaces the previous workbook."""
    base = os.path.join(sync.data_dir(), "schedule")
    pdfs = [i for i in items if i[0].lower().endswith(".pdf")]
    books = [i for i in items if i[0].lower().endswith(sync.XLSX)]
    replace_files(os.path.join(base, "dgca"), pdfs, (".pdf", ".csv"))
    replace_files(base, books, sync.XLSX)
    return [n for n, _ in items if not n.lower().endswith((".pdf",) + sync.XLSX)]


def rate_carrier(source, name):
    try:
        return parsers.detect_carrier(name, openpyxl.load_workbook(source, read_only=True).sheetnames)
    except Exception:  # noqa: BLE001 - unreadable file: the loader reports it
        return None


def save_rates(items):
    """The Allcargo sheet and the Akasa special-rates PDF replace their previous versions; an airline's
    tariff replaces the previous tariff for the same airline."""
    base = sync.data_dir()
    special = [i for i in items if i[0].lower().endswith(".pdf")]
    books = [i for i in items if i[0].lower().endswith(sync.XLSX)]
    quotes = [i for i in books if allcargo.is_quote(io.BytesIO(i[1]))]
    tariffs = [i for i in books if i not in quotes]
    replace_files(os.path.join(base, "special"), special, (".pdf",))
    replace_files(os.path.join(base, "allcargo"), quotes, sync.XLSX)
    folder = os.path.join(base, "rates")
    new = {rate_carrier(io.BytesIO(data), name) for name, data in tariffs} - {None}
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if rate_carrier(os.path.join(folder, name), name) in new:
                os.remove(os.path.join(folder, name))
    replace_files(folder, tariffs, ())
    return [n for n, _ in items if not n.lower().endswith((".pdf",) + sync.XLSX)]


def apply_upload(save, uploads, what):
    """Save the files, rebuild the schedule from them, then keep them on GitHub for after a restart."""
    items = expand(uploads)
    skipped = save(items)
    sig = data_signature()
    _, result = build_database(sig)
    extras_errors = load_extras(sig)[2]
    gh = github_store()
    saved = None
    if gh is not None:
        try:
            with st.spinner("Saving to GitHub…"):
                gh.push(sync.data_dir(), f"Upload {what}: " + ", ".join(n for n, _ in items))
            saved = True
        except Exception as e:  # noqa: BLE001 - shown to Ashita
            saved = f"{e}"
    ss["_upload_report"] = (result, saved, [n for n, _ in items if n not in skipped], skipped, extras_errors)
    st.rerun()


ss = st.session_state
is_admin = ss.get("username") == ADMIN_USER
today = dt.date.today()

restore_error = restore_uploads()
signature = data_signature()
db_path, sync_result = build_database(signature)
quote, special, extras_errors = load_extras(signature)
conn = db.connect(db_path)
sched_info = queries.schedule_info(conn, today)

if is_admin:
    with st.sidebar:
        st.header("Upload")
        with st.form("schedule", clear_on_submit=True, border=False):
            scheds = st.file_uploader("Upload schedule", type=["pdf", "xlsx", "xlsm", "zip"],
                                      accept_multiple_files=True,
                                      help="DGCA approved-schedule PDFs (or a .zip of them) give the flights; "
                                           "upload every airline's PDF together, they replace the previous ones. "
                                           "Reading them takes a few minutes. The ATC/AOC schedule workbook gives "
                                           "station names, and replaces the previous one.")
            if st.form_submit_button("Load schedule", width="stretch") and scheds:
                apply_upload(save_schedule, scheds, "schedule")
        with st.form("rates", clear_on_submit=True, border=False):
            files = st.file_uploader("Upload tariff rates", type=["xlsx", "pdf", "zip"], accept_multiple_files=True,
                                     help="Airline tariffs (.xlsx: IndiGo, Air India, Akasa, SpiceJet, Star Air), "
                                          "the Allcargo rate quotation (.xlsx) for Terminal & Surcharges, and the "
                                          "Akasa special rates (.pdf), or a .zip of them. Each file replaces the "
                                          "previous one of its kind (same airline for tariffs).")
            if st.form_submit_button("Load tariff rates", width="stretch") and files:
                apply_upload(save_rates, files, "tariff rates")
        # Say what happened only right after an upload, not on every page view.
        report = ss.pop("_upload_report", None)
        if report:
            result, saved, received, skipped, _ = report
            st.success("Received: " + "; ".join(received))
            if skipped:
                st.warning("Not used (unknown file type): " + "; ".join(skipped))
            if saved is True:
                st.success("Saved. Everyone sees this data until you upload again.")
            elif saved:
                st.error(f"Showing the new data, but it couldn't be saved to GitHub, so it will be lost when the "
                         f"app restarts: {saved}")
        for e in sync_result["errors"] + extras_errors:
            st.error(e)
        if restore_error:
            st.error(restore_error)
        if github_store() is None:
            st.warning("Saving is off: add the [github] section to Streamlit Secrets (see secrets.toml.example). "
                       "Until then, uploads are lost when the app restarts.")
        st.divider()
        st.caption("**Rates in use**")
        for carrier, b in queries.latest_batches(conn).items():
            st.caption(f"{carrier}: eff. {dmy(b['EffectiveDate'])}" if b else f"{carrier}: none loaded")
        st.caption(f"Allcargo T&S: {quote['file']}" if quote else "Allcargo T&S: none loaded")
        st.caption(f"Akasa special: {special['file']}" if special else "Akasa special: none loaded")
        st.caption(f"Schedule: {sched_info['label']} · {sched_info['flights']:,} flights")
        if sched_info["expired"]:
            st.warning(f"The {sched_info['label']} schedule ended on {dmy(sched_info['valid_to'])}. Flights are "
                       "shown as on its last day. Upload the new season's DGCA schedule PDFs.")

top = st.columns([6, 2, 1], vertical_alignment="center")
top[1].caption(f"Signed in as **{esc(ss.get('name'))}**")
with top[2]:
    authenticator.logout("Sign out", use_container_width=True)
if not ss.get("authentication_status"):
    st.rerun()  # just signed out -> back to the login screen

hubs, stations = queries.stations(conn)
if not stations:
    st.html(SHEET_CSS + TITLE)
    st.info("No data yet. Upload the schedule and the tariff rates from the sidebar." if is_admin else
            "No data yet. The flight schedule appears here once the schedule and tariff rates are uploaded.")
    st.stop()

eng = TariffEngine(conn, today)
names = {s["Code"]: s["Name"] or "" for s in stations}
hub_codes = [s["Code"] for s in hubs] or list(names)
all_codes = queries.destinations(conn, hub_codes) or list(names)

if not ss.get("_from_link"):  # a shared link like ?from=DEL&to=BOM opens that route once per session
    ss["_from_link"] = True
    if st.query_params.get("from", "").upper() in hub_codes:
        ss["origin"] = st.query_params["from"].upper()
    if st.query_params.get("to", "").upper() in all_codes:
        ss["dest"] = st.query_params["to"].upper()
if ss.get("origin") not in hub_codes:
    ss["origin"] = "DEL" if "DEL" in hub_codes else hub_codes[0]
if ss.get("dest") not in all_codes:
    ss["dest"] = "CJB" if "CJB" in all_codes else all_codes[0]

st.html(SHEET_CSS + WIDGET_CSS + TITLE)
c = st.columns([1.1, 1.1, 2, 1.4, 1.1, 2], vertical_alignment="center")
c[0].html('<div class="xl xl-label">Origin:</div>')
origin = c[1].selectbox("Origin", hub_codes, key="origin", label_visibility="collapsed")
c[2].html(f'<div class="xl xl-name">{esc(names.get(origin))}</div>')
c[3].html('<div class="xl xl-label">Destination:</div>')
dest = c[4].selectbox("Destination", all_codes, key="dest", label_visibility="collapsed")
c[5].html(f'<div class="xl xl-name">{esc(names.get(dest))}</div>')
st.query_params.from_dict({"from": origin, "to": dest})

flights = queries.route_flights(conn, origin, dest, today) if origin != dest else []
results = eng.price_all(flights)
weekly = sum(queries.weekly_frequency(r.flight) for r in results)
status = "SAME CITY" if origin == dest else ("ACTIVE" if weekly else "NO SERVICE")

sched_note = sched_info["label"] + (f" (as on {dmy(sched_info['date'])})"
                                   if sched_info["date"] and sched_info["date"] != today else "")
rate_effs = " · ".join(f"{c} {dmy(b['EffectiveDate'])}" for c in queries.CARRIER_TABLES
                      if (b := eng.batch(c)))
extra_effs = " · ".join(x for x in (f"Allcargo T&S {quote['wef']}" if quote else "",
                                    f"Akasa special {special['wef']}" if special else "") if x)
rates_line = (f"Rates eff.: {rate_effs or '–'}" + (f" | {extra_effs}" if extra_effs else "")
              + f"  |  Schedule: {sched_note}  |  Linked {dmy(today)}")
msg = {"SAME CITY": "⚠&nbsp; Please select two different cities as Origin and Destination.",
       "NO SERVICE": "✈&nbsp; No nonstop flights currently operate on this route. "
                     "Please try a different Origin / Destination combination."}.get(status, "")
if status == "ACTIVE" and not quote:
    msg = ("Terminal & Surcharges aren't loaded yet, so CPKG is blank. "
           + ("Upload the Allcargo sheet under Upload tariff rates." if is_admin else ""))


def price(r):
    """CPKG at 45+ and 100+: the airline's own tariff rate + Allcargo Terminal & Surcharges for this flight.
    On an Akasa special-rate route the special SSP rate is the 100+ rate. -> ({45: cell, 100: cell}, special)"""
    ts, ts_row = allcargo.terminal_surcharge(quote, r.flight, r.product)
    sp, sp_row = allcargo.special_rate(special, r.flight, r.product)
    if r.status in (STATUS_NO_TARIFF, STATUS_NO_RATE):
        sp = None
    cells = {}
    for brk in (45, 100):
        rate, used = r.rate_at(brk)
        what = f"tariff ({used})"
        if brk == 100 and sp:
            rate, used, what = sp["ssp"], "100+", f"Akasa special SSP rate ({sp_row.title()} flights)"
        if rate is None:
            cells[brk] = None
        elif ts is None:
            cells[brk] = {"v": None, "tip": f"{num(rate)} {what}; no Terminal & Surcharges for this flight in "
                                            "the Allcargo sheet"}
        else:
            src = "its own flight row" if ts_row == allcargo.flight_key(r.flight["FlightNo"]) else f"the {ts_row} row"
            cells[brk] = {"v": round(rate + ts, 2), "used": used,
                          "tip": f"{num(rate)} {what} + {num(ts)} terminal & surcharges (Allcargo, {src})"}
    return cells, sp


def lowest_key(cells):
    """The CPKG a row is compared on: 100+ kg, else 45+ kg."""
    for brk in (100, 45):
        if cells[brk] and cells[brk]["v"] is not None:
            return cells[brk]["v"]
    return None


priced = [(r, *price(r)) for r in results]
keys = [lowest_key(cells) for _, cells, _ in priced if lowest_key(cells) is not None]
lowest = min(keys) if keys else None

rows_html = []
for r, cells, sp in priced:
    f = r.flight
    if r.status == STATUS_NO_TARIFF:
        product, pcls = "No tariff", "c muted"
    elif r.status == STATUS_NO_RATE:
        product, pcls = "No rate", "c muted"
    else:
        product, pcls = r.product or "", "c check" if r.status == STATUS_CHECK else "c"
    badge = ' <span class="sp" title="Akasa special rate">SPECIAL</span>' if sp else ""
    tds = []
    for brk in (45, 100):
        cell = cells[brk]
        if cell is None:
            tds.append('<td class="cpkg"></td>')
        elif cell["v"] is None:
            tds.append(f'<td class="cpkg muted" title="{esc(cell["tip"])}">–</td>')
        else:
            mark = f"<sup>{cell['used']}</sup>" if cell["used"] != f"{brk}+" else ""
            tds.append(f'<td class="cpkg" title="{esc(cell["tip"])}">{num(cell["v"])}{mark}</td>')
    tr = '<tr class="lowest" title="Lowest CPKG on this route">' \
        if lowest is not None and lowest_key(cells) == lowest else "<tr>"
    rows_html.append(
        f"{tr}<td>{esc(f['Airline'])}</td><td class='c'>{esc(f['FlightNo'])}</td>"
        f"<td class='{pcls}' title='{esc(r.match_note)}'>{esc(product)}{badge}</td>"
        f"<td class='c'>{esc(f['DepTime'])}</td>{''.join(tds)}</tr>")

route_specials = sorted((k[3], v) for k, v in (special or {"rows": {}})["rows"].items()
                        if (k[0], k[1]) == (allcargo.station(origin), allcargo.station(dest)))
special_msg = ""
if route_specials and status == "ACTIVE":
    special_msg = ("★&nbsp; Akasa special rate on this route: "
                   + " · ".join(f"{cat.title()} flights SSP {num(v['ssp'])} (+100), Console {num(v['console'])}"
                                for cat, v in route_specials))

route = f"{esc(names.get(origin) or origin)} ({origin})&nbsp; → &nbsp;{esc(names.get(dest) or dest)} ({dest})"
table = ""
if rows_html:
    table = f"""
<div class="xl-wrap"><table class="xl-table">
  <thead>
<tr><th rowspan="2">AIRLINE</th><th rowspan="2">FLT NO.</th><th rowspan="2">PRODUCT</th><th rowspan="2">ETD</th>
    <th class="cpkg" colspan="2">CPKG &nbsp;(₹/kg)</th></tr>
<tr><th class="cpkg">45+ kg</th><th class="cpkg">100+ kg</th></tr>
  </thead>
  <tbody>{''.join(rows_html)}</tbody>
</table></div>"""
st.html(SHEET_CSS + f"""
<div class="xl">
  <div class="xl-rates">{esc(rates_line)}</div>
  <div class="xl-band">
<div><div class="k">ROUTE</div><div class="v route">{route}</div></div>
<div><div class="k">WEEKLY FLIGHTS</div><div class="v">{weekly}</div></div>
<div><div class="k">FLIGHT COUNT</div><div class="v">{len(results)}</div></div>
<div style="background:{STATUS_FILL[status]}"><div class="k">STATUS</div><div class="v st">{status}</div></div>
  </div>
  {f'<div class="xl-msg">{msg}</div>' if msg else ''}
  {f'<div class="xl-special">{special_msg}</div>' if special_msg else ''}
  {table}
  <div class="xl-note">CPKG (₹/kg) = the airline's own tariff rate (45+ / 100+) + Terminal &amp; Surcharges from the
Allcargo sheet for that flight (its own flight row, else the route's ALL row). Hover a CPKG value to see its breakdown;
– = no Terminal &amp; Surcharges for that flight. <span class="sp">SPECIAL</span> = Akasa special rate: the SSP rate is
used for 100+ kg. Amber product = check the rate condition (hover it to see why). A small <b>N</b> means the tariff
has no 45+/100+ rate on that route, so the N rate is used. <span style="background:{LOWEST_RED};padding:0 4px">Red
row</span> = lowest CPKG on the route (100+ kg).</div>
</div>""")

if special and special["rows"]:
    with st.expander(f"Akasa special-rate routes ({len(special['rows'])}) · w.e.f. {special['wef']}"):
        body = "".join(
            f"<tr><td class='c'>{esc(o)}</td><td class='c'>{esc(d)}</td><td class='c'>{esc(cat.title())}</td>"
            f"<td class='cpkg'>{num(v['ssp'])}</td><td class='cpkg'>{num(v['console'])}</td></tr>"
            for (o, d, _, cat), v in sorted(special["rows"].items()))
        st.html(SHEET_CSS + f"""<div class="xl"><table class="xl-table">
<thead><tr><th>ORIGIN</th><th>DESTINATION</th><th>FLIGHTS</th><th class="cpkg">SSP RATE +100</th>
<th class="cpkg">CONSOLE RATE</th></tr></thead><tbody>{body}</tbody></table></div>""")
