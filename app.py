import copy
import datetime as dt
import hashlib
import html
import os
import re

import streamlit as st
import streamlit_authenticator as stauth

import allcargo
from tariffapp import database_path, db, queries, sync
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
# Everyone who signs in sees the schedule, built from the files in data/
# (see README). To change the data, replace those files in GitHub.
# =====================================================

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


@st.cache_resource(show_spinner="Loading the latest data…", max_entries=1)
def build_database(signature):
    """A fresh database from exactly the files in the data folder, shared by every visitor and rebuilt
    whenever the files change - so the schedule always shows exactly the files in data/."""
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
    for f in os.listdir(folder):  # databases built from older files
        if f.startswith("tariff-") and not f.startswith(os.path.basename(path)):
            os.remove(os.path.join(folder, f))
    return path, result


def data_signature():
    """Changes whenever a file in the data folder is added, replaced or removed."""
    paths = [os.path.join(root, n) for root, _, names in os.walk(sync.data_dir()) for n in names]
    return tuple(sorted((p, os.path.getsize(p), int(os.path.getmtime(p))) for p in paths))


def newest(folder, extensions):
    paths = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.lower().endswith(extensions)] if os.path.isdir(folder) else []
    return max(paths, key=lambda p: (os.path.getmtime(p), p), default=None)


@st.cache_resource(show_spinner="Loading the Allcargo, OCDC and special rates…", max_entries=1)
def load_extras(signature):
    """(Allcargo quotation, Akasa special rates, Akasa OCDC station charges, errors) from the data folder."""
    quote = special = None
    ocdc, errors = {}, []
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
        except Exception as e:  # noqa: BLE001 - shown on the page
            errors.append(f"{os.path.basename(path)}: {e}")
    rates = os.path.join(sync.data_dir(), "rates")
    for name in sorted(os.listdir(rates)) if os.path.isdir(rates) else []:
        if name.lower().endswith(sync.XLSX) and not ocdc:
            try:
                ocdc = allcargo.read_ocdc(os.path.join(rates, name))  # only the Akasa tariff has an OCDC sheet
            except Exception as e:  # noqa: BLE001 - shown on the page
                errors.append(f"{name}: {e}")
    return quote, special, ocdc, errors


ss = st.session_state
today = dt.date.today()

signature = data_signature()
db_path, sync_result = build_database(signature)
quote, special, ocdc, extras_errors = load_extras(signature)
conn = db.connect(db_path)
sched_info = queries.schedule_info(conn, today)

for e in sync_result["errors"] + extras_errors:
    st.error(f"Couldn't read {e}")

top = st.columns([6, 2, 1], vertical_alignment="center")
top[1].caption(f"Signed in as **{esc(ss.get('name'))}**")
with top[2]:
    authenticator.logout("Sign out", use_container_width=True)
if not ss.get("authentication_status"):
    st.rerun()  # just signed out -> back to the login screen

hubs, stations = queries.stations(conn)
if not stations:
    st.html(SHEET_CSS + TITLE)
    st.info("No data yet. Add the schedule and tariff files to the data folder (see README).")
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
    msg = "Terminal & Surcharges aren't loaded yet, so CPKG is blank. Add the Allcargo sheet to data/allcargo."


def category(cat):
    """'PRIME' -> 'Prime', 'ALL' -> 'All', 'GCR' stays 'GCR'."""
    return {"PRIME": "Prime", "ALL": "All"}.get(cat, cat)


def price(r):
    """CPKG at 45+ and 100+. Akasa: its tariff rate (surcharges are already in it) + the OCDC add-on (origin
    outbound + destination inbound terminal charges); where the special-rates file covers the flight, its
    Direct AWB rate replaces the 100+ rate, + the same add-on. Other airlines: their tariff rate + the
    Allcargo Terminal & Surcharges for the flight. -> ({45: cell, 100: cell}, special)"""
    f = r.flight
    if f["Airline"] == "AKASA":
        addon, how = allcargo.ocdc_addon(ocdc, f)
        sp, sp_kind = allcargo.special_rate(special, f, r.product)
        cells = {}
        for brk in (45, 100):
            rate, used = r.rate_at(brk)
            what = f"Akasa tariff ({used}, surcharge included)"
            if brk == 100 and sp:
                rate, used, what = sp["ssp"], "100+", f"special Direct AWB rate (+100, {category(sp_kind)} flights)"
            if rate is None:
                cells[brk] = None
            elif addon is None:
                cells[brk] = {"v": None, "tip": f"{num(rate)} {what}; no OCDC terminal charges for these stations"}
            else:
                cells[brk] = {"v": round(rate + addon, 2), "used": used,
                              "tip": f"{num(rate)} {what} + {num(addon)} add-on (OCDC: {how})"}
        return cells, sp
    row, key = allcargo.quote_row(quote, f, r.product, with_number=True)
    ts = row["ts"] if row else None
    src = "its own flight row" if key == allcargo.flight_key(f["FlightNo"]) else f"the {key} row"
    cells = {}
    for brk in (45, 100):
        rate, used = r.rate_at(brk)
        if rate is None:
            cells[brk] = None
        elif ts is None:
            cells[brk] = {"v": None, "tip": f"{num(rate)} tariff ({used}); no Terminal & Surcharges for this "
                                            "flight in the Allcargo sheet"}
        else:
            cells[brk] = {"v": round(rate + ts, 2), "used": used,
                          "tip": f"{num(rate)} tariff ({used}) + {num(ts)} terminal & surcharges (Allcargo, {src})"}
    return cells, None


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
                   + " · ".join(f"{category(cat)} flights {num(v['ssp'])} (Direct AWB +100, plus add-on)"
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
Allcargo sheet for that flight, matched by flight number (its own flight row, else its product's row, else the route's
ALL row). <b>Akasa</b>: Akasa tariff rate (surcharges already included) + add-on from Akasa's OCDC sheet (origin outbound +
destination inbound terminal charges, ₹/kg). <span class="sp">SPECIAL</span> = Akasa special rate: the Direct AWB rate is
used for 100+ kg, + the same add-on. Hover a CPKG value to see its breakdown; – = no Terminal &amp; Surcharges for that
flight. Amber product = check the rate condition (hover it to see why). A small <b>N</b> means the tariff has no
45+/100+ rate on that route, so the N rate is used. <span style="background:{LOWEST_RED};padding:0 4px">Red
row</span> = lowest CPKG on the route (100+ kg).</div>
</div>""")

if special and special["rows"]:
    with st.expander(f"Akasa special-rate routes ({len(special['rows'])}) · w.e.f. {special['wef']}"):
        body = "".join(
            f"<tr><td class='c'>{esc(o)}</td><td class='c'>{esc(d)}</td><td class='c'>{esc(category(cat))}</td>"
            f"<td class='cpkg'>{num(v['ssp'])}</td></tr>"
            for (o, d, _, cat), v in sorted(special["rows"].items()))
        st.html(SHEET_CSS + f"""<div class="xl"><table class="xl-table">
<thead><tr><th>ORIGIN</th><th>DESTINATION</th><th>FLIGHTS</th><th class="cpkg">DIRECT AWB +100</th></tr></thead>
<tbody>{body}</tbody></table></div>""")
