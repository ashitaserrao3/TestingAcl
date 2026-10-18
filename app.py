import copy
import datetime as dt
import html
import os
import re

import streamlit as st
import streamlit_authenticator as stauth

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


def get_conn():
    conn = db.connect(database_path())
    if not st.session_state.get("_schema_ok"):
        db.init_schema(conn)
        st.session_state["_schema_ok"] = True
    return conn


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


def save_to_data_folder(f, sub):
    """Store an upload in the data folder under its own name, so it is synced like any other file."""
    folder = os.path.join(sync.data_dir(), sub)
    os.makedirs(folder, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|]+', "_", os.path.basename(f.name)).strip() or "upload.xlsx"
    with open(os.path.join(folder, name), "wb") as out:
        out.write(f.getbuffer())
    return name


@st.cache_resource(show_spinner="Loading the latest data…")
def sync_data(signature):
    """Runs once per change of the data folder (signature), shared by every visitor."""
    c = db.connect(database_path())
    db.init_schema(c)
    try:
        return sync.sync_data_folder(c)
    finally:
        c.close()


conn = get_conn()
today = dt.date.today()
ss = st.session_state
is_admin = ss.get("username") == ADMIN_USER

sync_result = sync_data(sync.folder_signature())
sched_info = queries.schedule_info(conn, today)

if is_admin:
    with st.sidebar:
        st.header("Upload")
        with st.form("schedule", clear_on_submit=True, border=False):
            scheds = st.file_uploader("Upload schedule", type=["pdf", "xlsx", "xlsm"], accept_multiple_files=True,
                                      help="DGCA approved-schedule PDFs (one per airline) give the flights; reading "
                                           "them takes a few minutes. The ATC/AOC schedule workbook gives station "
                                           "names, Add-on Rates and Network Surcharges.")
            if st.form_submit_button("Load schedule", width="stretch") and scheds:
                for f in scheds:
                    save_to_data_folder(f, "schedule/dgca" if f.name.lower().endswith(".pdf") else "schedule")
                ss["_just_uploaded"] = True
                st.cache_resource.clear()
                st.rerun()
        with st.form("rates", clear_on_submit=True, border=False):
            files = st.file_uploader("Upload tariff rates", type=["xlsx"], accept_multiple_files=True,
                                     help="IndiGo, Air India, Akasa, SpiceJet or Star Air tariff (.xlsx). "
                                          "Files already loaded are skipped.")
            if st.form_submit_button("Load tariff rates", width="stretch") and files:
                for f in files:
                    save_to_data_folder(f, "rates")
                ss["_just_uploaded"] = True
                st.cache_resource.clear()
                st.rerun()
        # Say what was loaded only right after an upload, not on every page view.
        if ss.pop("_just_uploaded", False) and (sync_result["schedule"] or sync_result["dgca"]
                                                or sync_result["rates_loaded"]):
            loaded = [f"schedule {sync_result['schedule']}"] if sync_result["schedule"] else []
            loaded += [sync_result["dgca"]] if sync_result["dgca"] else []
            loaded += sync_result["rates_loaded"]
            st.success("Loaded: " + "; ".join(loaded))
        for e in sync_result["errors"]:
            st.error(e)
        st.divider()
        st.caption("**Rates in use**")
        for carrier, b in queries.latest_batches(conn).items():
            st.caption(f"{carrier}: eff. {dmy(b['EffectiveDate'])}" if b else f"{carrier}: none loaded")
        st.caption(f"Schedule: {sched_info['label']} · {sched_info['flights']:,} flights")
        if sched_info["expired"]:
            st.warning(f"The {sched_info['label']} schedule ended on {dmy(sched_info['valid_to'])}. Flights are "
                       "shown as on its last day. Upload the new season's DGCA schedule PDFs.")
        st.caption("Uploaded files last until the app restarts. After a restart, upload them again.")

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

# Add-ons (X-ray, TSP, handling...): defaults from the workbook's Add-on Rates sheet; anyone can try their
# own values here. Only CPKG changes - tariff and surcharges (fuel, sector...) stay as they are.
addon_airlines = [(code, a["TariffCarrier"], a["AddOnPerKg"] or 0.0) for code, a in eng.airlines.items()
                  if a.get("TariffCarrier")]
addon_airlines.sort(key=lambda x: list(queries.CARRIER_TABLES).index(x[1])
                    if x[1] in queries.CARRIER_TABLES else 99)
for code, _, default in addon_airlines:
    ss.setdefault(f"addon_{code}", float(default))
custom = [code for code, _, default in addon_airlines if ss[f"addon_{code}"] != float(default)]
with st.expander("Add-on ₹/kg (X-ray, TSP, handling)" + (" · your own values" if custom else ""),
                 expanded=bool(custom)):
    cols = st.columns(len(addon_airlines) + 1, vertical_alignment="bottom")
    for col, (code, carrier, default) in zip(cols, addon_airlines):
        col.number_input(carrier, min_value=0.0, step=0.5, format="%.2f", key=f"addon_{code}",
                         help=f"Default {default:g} (from the workbook's Add-on Rates sheet)")
    cols[-1].button("Reset", width="stretch", key="addon_reset", disabled=not custom,
                    on_click=lambda: ss.update({f"addon_{c}": float(d) for c, _, d in addon_airlines}))
for code, _, _ in addon_airlines:
    eng.airlines[code]["AddOnPerKg"] = ss[f"addon_{code}"]

flights = queries.route_flights(conn, origin, dest, today) if origin != dest else []
results = eng.price_all(flights)
weekly = sum(queries.weekly_frequency(r.flight) for r in results)
status = "SAME CITY" if origin == dest else ("ACTIVE" if weekly else "NO SERVICE")

sched_note = sched_info["label"] + (f" (as on {dmy(sched_info['date'])})"
                                   if sched_info["date"] and sched_info["date"] != today else "")
rate_effs = " · ".join(f"{c} {dmy(b['EffectiveDate'])}" for c in queries.CARRIER_TABLES
                      if (b := eng.batch(c)))
rates_line = f"Rates eff.: {rate_effs or '–'}  |  Schedule: {sched_note}  |  Linked {dmy(today)}"
msg = {"SAME CITY": "⚠&nbsp; Please select two different cities as Origin and Destination.",
       "NO SERVICE": "✈&nbsp; No nonstop flights currently operate on this route. "
                     "Please try a different Origin / Destination combination."}.get(status, "")


def lowest_key(r):
    """The CPKG a row is compared on: 100+ kg, else 45+ kg."""
    return r.cpkg(100)[0] if r.cpkg(100)[0] is not None else r.cpkg(45)[0]


priced = [lowest_key(r) for r in results if lowest_key(r) is not None]
lowest = min(priced) if priced else None

rows_html = []
for r in results:
    f = r.flight
    if r.status == STATUS_NO_TARIFF:
        product, pcls = "No tariff", "c muted"
    elif r.status == STATUS_NO_RATE:
        product, pcls = "No rate", "c muted"
    else:
        product, pcls = r.product or "", "c check" if r.status == STATUS_CHECK else "c"
    cells = []
    for brk in (45, 100):
        v, used = r.cpkg(brk)
        if v is None:
            cells.append('<td class="cpkg"></td>')
            continue
        rate, _ = r.rate_at(brk)
        tip = (f"{num(rate)} tariff ({used}) + {num(r.surcharge_total)} surcharge "
               f"[{r.surcharge_summary or 'none'}] + {num(r.addon or 0)} add-on")
        mark = f"<sup>{used}</sup>" if used != f"{brk}+" else ""
        cells.append(f'<td class="cpkg" title="{esc(tip)}">{num(v)}{mark}</td>')
    tr = '<tr class="lowest" title="Lowest CPKG on this route">' \
        if lowest is not None and lowest_key(r) == lowest else "<tr>"
    rows_html.append(
        f"{tr}<td>{esc(f['Airline'])}</td><td class='c'>{esc(f['FlightNo'])}</td>"
        f"<td class='{pcls}' title='{esc(r.match_note)}'>{esc(product)}</td>"
        f"<td class='c'>{esc(f['DepTime'])}</td>{''.join(cells)}</tr>")

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
  {table}
  <div class="xl-note">CPKG (₹/kg) = tariff rate + surcharge + add-on (X-ray/TSP/handling). Hover a CPKG value to see
its breakdown. Amber product = check the rate condition (hover it to see why). A small <b>N</b> means the tariff
has no 45+/100+ rate on that route, so the N rate is used. <span style="background:{LOWEST_RED};padding:0 4px">Red
row</span> = lowest CPKG on the route (100+ kg).</div>
</div>""")
