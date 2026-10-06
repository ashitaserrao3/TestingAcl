import altair as alt
import pandas as pd
import streamlit as st

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


# on-screen names for the CHR_WT / TOTAL_FRT columns (the Excel export keeps the standard names)
WT_HEADER, FRT_HEADER = "Chg. Wt (kg)", "Total Frt (₹)"

FILTER_COLS = ["AGENT", "ORIGIN", "DEST", "BILL_PERIOD", "TRNSPT_MODE"]


def apply_filters(df, key):
    filters = FILTER_COLS[1:]
    if df["AGENT"].nunique() > 1:
        filters = FILTER_COLS
    labels = {"AGENT": "Agent", "ORIGIN": "Origin", "DEST": "Destination", "BILL_PERIOD": "Bill period",
              "TRNSPT_MODE": "Transport mode"}

    cols = st.columns(len(filters))
    filtered = df
    for col_ui, col in zip(cols, filters):
        with col_ui:
            choice = st.selectbox(labels[col], _options(df, col), key=f"{key}_{col}")
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


def agent_chart(in_table, agents, key):
    """'View' button under the agent table -> share-% bars per agent."""
    if not view_toggle(key, "agent_chart", in_table, "📊 View", "Hide chart"):
        return
    if in_table.empty:  # e.g. Road: no Console / Direct rows to chart
        st.caption("No Console / Direct shipments for these filters, so there is nothing to chart.")
        return

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
    shares = pd.DataFrame(rows)

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

    section("Lodgement · Volume · Cost share by agent")
    st.altair_chart(share_chart, width="stretch")


def show_dashboard(df, key="dash"):
    """Filters + KPIs + slab matrix + lane summary. Returns the filtered rows."""
    filtered = apply_filters(df, key)

    # ---------------- KPIs ----------------
    k = st.columns(4)
    k[0].metric("AWBs", _n(len(filtered)))
    k[1].metric("Total freight (₹)", _n(filtered["TOTAL_FRT"].sum()))
    k[2].metric("Chargeable weight (kg)", _n(filtered["CHR_WT"].sum(), 1))
    k[3].metric("CPKG (₹/kg)", _n(_cpkg(filtered), 2))

    # ---------------- SLAB × MODE ----------------
    # Road has no Console / Direct, so road-only data gets plain tables without that split
    road_only = len(filtered) > 0 and (filtered["TRNSPT_MODE"].astype(str).str.upper() == "ROAD").all()
    split_title = "" if road_only else " · Console vs Direct"
    section("Slab-wise" + split_title)
    mode = filtered["LODGE_MODE"].astype(str).str.upper()
    lodged = filtered["SLAB"].notna() if road_only else mode.isin(["DIRECT", "CONSOLE"]) & filtered["SLAB"].notna()
    in_table = filtered[lodged]
    grand = (len(in_table), in_table["CHR_WT"].sum(), in_table["TOTAL_FRT"].sum())

    def pct(x, total):
        return f"{x / total:.0%}" if total else "–"

    def cells(part):
        n, wt, frt = len(part), part["CHR_WT"].sum(), part["TOTAL_FRT"].sum()
        return [_n(n), pct(n, grand[0]), _n(wt), pct(wt, grand[1]), _n(frt), pct(frt, grand[2]),
                _n(_cpkg(part), 2) if n else '<span class="acl-muted">–</span>']

    headers = ["Lodge mode", "Lodgements", "Lodgement %", WT_HEADER, "Volume %", FRT_HEADER, "Cost %", "CPKG"]

    def pivot(first_header, parts):
        """parts: (title, rows of in_table) -> one foldable group each: total on top, Console / Direct underneath.
        Road-only data: one plain row per part."""
        if road_only:
            html_table(
                [first_header] + headers[1:], [[title] + cells(part) for title, part in parts],
                total_row=["Grand Total"] + cells(in_table), group_starts=(1, 3, 5, 7), text_cols=(0,),
            )
            return
        groups = []
        for title, part in parts:
            pmode = part["LODGE_MODE"].astype(str).str.upper()
            details = [["", label] + cells(part[pmode == name])
                       for name, label in [("CONSOLE", "Console"), ("DIRECT", "Direct")]]
            groups.append(([title, ""] + cells(part), details))
        html_table(
            [first_header] + headers, None, total_row=["Grand Total", ""] + cells(in_table),
            group_starts=(2, 4, 6, 8), text_cols=(0, 1), fold_groups=groups,
        )

    pivot("Slab", [(title, in_table[in_table["SLAB"].isin(slabs)]) for title, slabs in SLAB_GROUPS.items()])

    other = filtered[~mode.isin(["DIRECT", "CONSOLE"])] if not road_only else filtered.iloc[0:0]
    notes = []
    if len(other):
        split = other["LODGE_MODE"].value_counts().to_dict()
        notes.append(f"{len(other):,} rows not Direct/Console ({', '.join(f'{k}: {v}' for k, v in split.items())})")
    no_slab = int(filtered["SLAB"].isna().sum())
    if no_slab:
        notes.append(f"{no_slab:,} rows without weight")
    if notes:
        st.caption("Not in the table above: " + " · ".join(notes))

    # ---------------- AGENT × MODE ----------------
    if filtered["AGENT"].nunique() > 1:
        section("Agent-wise" + split_title)
        by_frt = in_table.groupby("AGENT")["TOTAL_FRT"].sum().sort_values(ascending=False).index
        pivot("Agent", [(a, in_table[in_table["AGENT"] == a]) for a in by_frt])
        agent_chart(in_table, list(by_frt), key)

    # ---------------- LANES: costliest / cheapest by CPKG, high vs low volume ----------------
    lanes = (
        filtered.dropna(subset=["OD_PAIR"])
        .groupby("OD_PAIR")
        .agg(AWBs=("AWB_NO", "size"), CHR_WT=("CHR_WT", "sum"), TOTAL_FRT=("TOTAL_FRT", "sum"))
        .reset_index()
    )
    lanes = lanes[lanes["CHR_WT"] > 0]
    lanes["CPKG"] = lanes["TOTAL_FRT"] / lanes["CHR_WT"]

    # split lanes into high / low volume (chargeable weight above / below the median lane)
    high_vol = lanes[lanes["CHR_WT"] >= lanes["CHR_WT"].median()]
    low_vol = lanes[lanes["CHR_WT"] < lanes["CHR_WT"].median()]

    def lane_rows(top):
        if top.empty:
            return [['<span class="acl-muted">No lanes match</span>', "", "", "", ""]]
        return [[f"<b>{r.OD_PAIR}</b>", _n(r.AWBs), _n(r.CHR_WT), _n(r.TOTAL_FRT), f"<b>{_n(r.CPKG, 2)}</b>"]
                for r in top.itertuples()]

    def top_bottom(group):
        """Costliest and cheapest 10 by CPKG; fewer than 20 lanes -> split so none shows in both."""
        n_up, n_down = min(10, (len(group) + 1) // 2), min(10, len(group) // 2)
        return group.nlargest(n_up, "CPKG"), group.nsmallest(n_down, "CPKG")

    hv_up, hv_down = top_bottom(high_vol)
    lv_up, lv_down = top_bottom(low_vol)
    lane_headers = ["Lane (OD)", "AWBs", WT_HEADER, FRT_HEADER, "CPKG"]
    for (l_title, l_rows, tone), (r_title, r_rows, _) in [
        (("Top 10 lanes · ↑ High vol · ↑ CPKG", hv_up, "red"), ("Top 10 lanes · ↓ Low vol · ↑ CPKG", lv_up, "red")),
        (("Top 10 lanes · ↑ High vol · ↓ CPKG", hv_down, "green"), ("Top 10 lanes · ↓ Low vol · ↓ CPKG", lv_down, "green")),
    ]:
        left, right = st.columns(2)
        with left:
            section(l_title)
            html_table(lane_headers, lane_rows(l_rows), tone=tone)
        with right:
            section(r_title)
            html_table(lane_headers, lane_rows(r_rows), tone=tone)
    return filtered
