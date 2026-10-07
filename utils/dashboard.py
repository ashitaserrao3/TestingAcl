import hashlib
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from utils.activity_log import log_event
from utils import pdf_report
from utils.pdf_report import build_pdf
from utils.ui import html_table, section

SLAB_GROUPS = {
    "Less than 45Kg": ["Less than 45Kg"],
    "45Kg +": ["45Kg +"],
    "100Kg & above": ["100Kg +", "250Kg +", "300Kg +", "500Kg +", "1000Kg +"],
}


def _cpkg(frame):
    wt = frame["CHR_WT"].sum()
    return frame["TOTAL_FRT"].sum() / wt if wt else 0


def _options(df, col):
    return ["All"] + sorted(df[col].dropna().astype(str).unique().tolist())


def _n(x, dp=0):
    return f"{x:,.{dp}f}"


_CODE_VERSION = hashlib.md5(Path(__file__).read_bytes() + Path(pdf_report.__file__).read_bytes()).hexdigest()

# on-screen names for the CHR_WT / TOTAL_FRT columns (the Excel export keeps the standard names)
WT_HEADER, FRT_HEADER = "Charged Weight", "Total Freight"

FILTER_COLS = ["AGENT", "ORIGIN", "DEST", "BILL_PERIOD", "TRNSPT_MODE"]
FILTER_LABELS = {"AGENT": "Agent", "ORIGIN": "Origin", "DEST": "Destination", "BILL_PERIOD": "Bill period",
                 "TRNSPT_MODE": "Transport mode"}


def apply_filters(df, key):
    filters = FILTER_COLS[1:]
    if df["AGENT"].nunique() > 1:
        filters = FILTER_COLS

    cols = st.columns(len(filters))
    filtered = df
    for col_ui, col in zip(cols, filters):
        with col_ui:
            choice = st.selectbox(FILTER_LABELS[col], _options(df, col), key=f"{key}_{col}")
        if choice != "All":
            filtered = filtered[filtered[col].astype(str) == choice]
    return filtered


# one colour per measure, same order everywhere (blue, orange, aqua)
SHARE_COLORS = {"Lodgement %": "#2a78d6", "Volume %": "#eb6834", "Cost %": "#1baf7a"}


def _short(x):
    """Compact Indian-style number for bar labels: 1,492 -> 1.5K, 6,679,852 -> 66.8L, 2.3 crore -> 2.30Cr."""
    if x >= 1e7:
        return f"{x / 1e7:.2f}Cr"
    if x >= 1e5:
        return f"{x / 1e5:.1f}L"
    if x >= 1e3:
        return f"{x / 1e3:.1f}K"
    return f"{x:.0f}"


def _tonnes(kg):
    """Bar label for weight: 293,720 kg -> '294 T', 4,675 kg -> '4.7 T', 72 kg -> '0.07 T'."""
    t = kg / 1000
    if t >= 100:
        return f"{t:,.0f} T"
    if t >= 1:
        return f"{t:.1f} T"
    return f"{t:.2f} T"


def _flip(state_key):
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def view_toggle(key, name, data, view_label, hide_label):
    """View / Hide button. Returns True while open; closes again whenever the filters or data change."""
    state_key = f"{key}_{name}"
    filters = tuple(st.session_state.get(f"{key}_{col}") for col in FILTER_COLS)
    signature = (filters, len(data), float(data["TOTAL_FRT"].sum()))
    if st.session_state.get(f"{state_key}_sig") != signature:
        st.session_state[f"{state_key}_sig"] = signature
        st.session_state[state_key] = False
    showing = st.session_state.get(state_key, False)
    st.button(hide_label if showing else view_label, key=f"{state_key}_btn", on_click=_flip, args=(state_key,))
    return showing


CHART_TITLE = "Lodgement · Volume · Cost share by agent"


def share_data(in_table, agents):
    """One row per agent × measure: share %, short label for the bar, exact figure for the tooltip."""
    grand = {"Lodgement %": len(in_table), "Volume %": in_table["CHR_WT"].sum(),
             "Cost %": in_table["TOTAL_FRT"].sum()}
    rows = []
    for a in agents:
        part = in_table[in_table["AGENT"] == a]
        actual = {"Lodgement %": len(part), "Volume %": part["CHR_WT"].sum(), "Cost %": part["TOTAL_FRT"].sum()}
        exact = {"Lodgement %": _n(actual["Lodgement %"]), "Volume %": f"{_n(actual['Volume %'])} kg",
                 "Cost %": f"₹{_n(actual['Cost %'])}"}
        short = {"Lodgement %": exact["Lodgement %"], "Volume %": _tonnes(actual["Volume %"]),
                 "Cost %": f"₹{_short(actual['Cost %'])}"}
        for measure in SHARE_COLORS:
            share = actual[measure] / grand[measure] * 100 if grand[measure] else 0
            rows.append({"Agent": a, "Measure": measure, "Share": share,
                         "Pct": f"{share:.0f}%", "Actual": short[measure], "Exact": exact[measure]})
    return pd.DataFrame(rows)


def agent_chart(in_table, agents, key):
    """'View' button under the agent table -> share-% bars per agent."""
    if not view_toggle(key, "agent_chart", in_table, "📊 View", "Hide chart"):
        return
    if in_table.empty:
        st.caption("No shipments for these filters, so there is nothing to chart.")
        return
    shares = share_data(in_table, agents)

    axis_x = alt.Axis(labelAngle=0, title=None, labelColor="#33415C", domain=False, ticks=False)
    axis_y = dict(grid=True, gridColor="#EEF1F6", domain=False, ticks=False, labelColor="#5B6B82",
                  titleColor="#5B6B82")

    base = alt.Chart(shares).encode(
        x=alt.X("Agent:N", sort=agents, axis=axis_x),
        xOffset=alt.XOffset("Measure:N", sort=list(SHARE_COLORS)),
        y=alt.Y("Share:Q", title="Share of total (%)", axis=alt.Axis(**axis_y),
                scale=alt.Scale(domainMax=shares["Share"].max() * 1.18 if len(shares) else 100)),
        tooltip=["Agent", "Measure", alt.Tooltip("Share:Q", title="Share %", format=".1f"),
                 alt.Tooltip("Exact:N", title="Actual")],
    )
    bars = base.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, stroke="#FFFFFF", strokeWidth=2).encode(
        color=alt.Color("Measure:N", sort=list(SHARE_COLORS),
                        scale=alt.Scale(domain=list(SHARE_COLORS), range=list(SHARE_COLORS.values())),
                        legend=alt.Legend(orient="top", title=None, labelColor="#33415C")),
    )
    # % on top (bold), actual number just under it
    pct = base.mark_text(dy=-20, fontSize=11, fontWeight="bold", color="#14213D").encode(text="Pct:N")
    actual = base.mark_text(dy=-7, fontSize=10, color="#5B6B82").encode(text="Actual:N")
    share_chart = (bars + pct + actual).properties(height=360)

    section(CHART_TITLE)
    st.altair_chart(share_chart, width="stretch")


def show_dashboard(df, key="dash", pdf_name="Dashboard.pdf", month=None):
    """Filters + KPIs + slab matrix + lane summary + PDF download. Returns the filtered rows."""
    filtered = apply_filters(df, key)
    _, pdf_col = st.columns([4, 1])
    pdf_slot = pdf_col.empty()  # filled at the end, once everything below is worked out
    report = []  # what the dashboard shows, for the PDF

    # ---------------- KPIs ----------------
    kpis = [("AWBs", _n(len(filtered))), ("Total freight (₹)", _n(filtered["TOTAL_FRT"].sum())),
            ("Chargeable weight (kg)", _n(filtered["CHR_WT"].sum(), 1)), ("CPKG (₹/kg)", _n(_cpkg(filtered), 2))]
    for col, (label, value) in zip(st.columns(4), kpis):
        col.metric(label, value)
    report.append(("kpis", kpis))

    # ---------------- SLAB × MODE ----------------
    # the Console / Direct split only applies to air: shown when Transport mode = AIR, plain tables otherwise
    air_split = str(st.session_state.get(f"{key}_TRNSPT_MODE", "")).upper() == "AIR"
    split_title = " · Console vs Direct" if air_split else ""
    slab_title = "Slab-wise" + split_title
    section(slab_title)
    # every filtered row is in the tables, so the Grand Total always matches the KPI boxes above
    in_table = filtered
    grand = (len(in_table), in_table["CHR_WT"].sum(), in_table["TOTAL_FRT"].sum())
    # sub-row per slab / agent: Console and Direct, plus Other when the air data has any
    mode = filtered["LODGE_MODE"].astype(str).str.upper()
    category = pd.Series("Other", index=filtered.index)
    category[mode == "CONSOLE"], category[mode == "DIRECT"] = "Console", "Direct"
    category[filtered["TRNSPT_MODE"].astype(str).str.upper() == "ROAD"] = "Road"
    sub_rows = ["Console", "Direct"] + [c for c in ("Road", "Other") if (category == c).any()]

    def pct(x, total):
        return f"{x / total:.0%}" if total else "–"

    def cells(part):
        n, wt, frt = len(part), part["CHR_WT"].sum(), part["TOTAL_FRT"].sum()
        return [_n(n), pct(n, grand[0]), _n(wt), pct(wt, grand[1]), _n(frt), pct(frt, grand[2]),
                _n(_cpkg(part), 2) if wt else '<span class="acl-muted">–</span>']

    headers = ["Lodge mode", "Lodgements", "Lodgement %", WT_HEADER, "Volume %", FRT_HEADER, "Cost %", "CPKG"]

    def pivot(table_title, first_header, parts):
        """parts: (title, rows of in_table) -> one foldable group each: total on top, Console / Direct
        (and Other) underneath. Not filtered to AIR: one plain row per part."""
        if not air_split:
            rows = [[title] + cells(part) for title, part in parts]
            total = ["Grand Total"] + cells(in_table)
            html_table([first_header] + headers[1:], rows, total_row=total, group_starts=(1, 3, 5, 7), text_cols=(0,))
            report.append(("table", table_title, [first_header] + headers[1:], [("", r) for r in rows], total))
            return
        groups = []
        for title, part in parts:
            details = [["", label] + cells(part[category[part.index] == label]) for label in sub_rows]
            groups.append(([title, ""] + cells(part), details))
        total = ["Grand Total", ""] + cells(in_table)
        html_table(
            [first_header] + headers, None, total_row=total,
            group_starts=(2, 4, 6, 8), text_cols=(0, 1), fold_groups=groups,
        )
        pdf_rows = [row for summary, details in groups
                    for row in [("sub", summary)] + [("detail", d) for d in details]]
        report.append(("table", table_title, [first_header] + headers, pdf_rows, total))

    slab_parts = [(title, in_table[in_table["SLAB"].isin(slabs)]) for title, slabs in SLAB_GROUPS.items()]
    if in_table["SLAB"].isna().any():
        slab_parts.append(("No weight", in_table[in_table["SLAB"].isna()]))
    pivot(slab_title, "Slab", slab_parts)

    notes = []
    if air_split and "Other" in sub_rows:
        notes.append("Other = air shipments whose lodge mode is not Console or Direct")
    if in_table["SLAB"].isna().any():
        notes.append("No weight = rows without chargeable weight (their freight is counted, so CPKG matches the totals)")
    if notes:
        st.caption(" · ".join(notes))
        report.append(("note", " · ".join(notes)))

    # ---------------- AGENT × MODE ----------------
    if filtered["AGENT"].nunique() > 1:
        section("Agent-wise" + split_title)
        by_frt = in_table.groupby("AGENT")["TOTAL_FRT"].sum().sort_values(ascending=False).index
        pivot("Agent-wise" + split_title, "Agent", [(a, in_table[in_table["AGENT"] == a]) for a in by_frt])
        agent_chart(in_table, list(by_frt), key)
        if not in_table.empty:
            sd = share_data(in_table, list(by_frt))
            report.append(("chart", CHART_TITLE, list(by_frt),
                           {m: sd[sd["Measure"] == m]["Share"].tolist() for m in SHARE_COLORS},
                           {m: sd[sd["Measure"] == m]["Actual"].tolist() for m in SHARE_COLORS}))

    # ---------------- LANES: costliest / cheapest by CPKG ----------------
    lanes = (
        filtered.dropna(subset=["OD_PAIR"])
        .groupby("OD_PAIR")
        .agg(AWBs=("AWB_NO", "size"), CHR_WT=("CHR_WT", "sum"), TOTAL_FRT=("TOTAL_FRT", "sum"))
        .reset_index()
    )
    lanes = lanes[lanes["CHR_WT"] > 0]
    lanes["CPKG"] = lanes["TOTAL_FRT"] / lanes["CHR_WT"]

    # only busy lanes count: above-average lodgements AND volume for the current filters
    busy = lanes[(lanes["AWBs"] >= lanes["AWBs"].mean()) & (lanes["CHR_WT"] >= lanes["CHR_WT"].mean())]

    def lane_rows(top):
        if top.empty:
            return [['<span class="acl-muted">No lanes match</span>', "", "", "", ""]]
        return [[f"<b>{r.OD_PAIR}</b>", _n(r.AWBs), _n(r.CHR_WT), _n(r.TOTAL_FRT), f"<b>{_n(r.CPKG, 2)}</b>"]
                for r in top.itertuples()]

    # fewer than 20 busy lanes -> split them so no lane shows in both tables
    n_red, n_green = min(10, (len(busy) + 1) // 2), min(10, len(busy) // 2)
    lane_headers = ["Lane (OD)", "AWBs", WT_HEADER, FRT_HEADER, "CPKG"]
    lane_tables = [("Top 10 lanes by ↑ CPKG", lane_rows(busy.nlargest(n_red, "CPKG")), "red"),
                   ("Top 10 lanes by ↓ CPKG", lane_rows(busy.nsmallest(n_green, "CPKG")), "green")]
    for col, (title, rows, tone) in zip(st.columns(2), lane_tables):
        with col:
            section(title)
            html_table(lane_headers, rows, tone=tone)
    lane_tables = [(title, lane_headers, [("", r) for r in rows], tone) for title, rows, tone in lane_tables]
    report.append(("lanes", lane_tables))

    # ---------------- PDF of everything above ----------------
    pdf_slot.download_button(
        "⬇  Download PDF", data=dashboard_pdf(report, filtered, key, month), file_name=pdf_name,
        mime="application/pdf", key=f"{key}_pdf", type="primary", width="stretch", on_click=log_event, args=("DOWNLOAD", pdf_name),
    )
    return filtered


def dashboard_pdf(report, filtered, key, month):
    """PDF bytes for the current view; built once per view and kept for the session."""
    filters = [f"{FILTER_LABELS[c]}: {st.session_state[f'{key}_{c}']}" for c in FILTER_COLS
               if st.session_state.get(f"{key}_{c}") not in (None, "All")]
    agents = sorted(filtered["AGENT"].dropna().unique())
    subtitle = [", ".join(agents) or "No agents", month or "All months"] + (filters or ["No filters"])
    cache = st.session_state.setdefault(f"{key}_pdf_cache", {})
    # keyed on everything that goes into the PDF, plus the code version, so an app update never
    # hands back a PDF built by older code
    sig = hashlib.md5(repr((_CODE_VERSION, subtitle, report)).encode()).hexdigest()
    if sig not in cache:
        cache.clear()
        cache[sig] = build_pdf(report, "ACL Air Cargo Bills", subtitle, SHARE_COLORS)
    return cache[sig]
