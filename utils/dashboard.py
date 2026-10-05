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


def apply_filters(df, key):
    filters = ["ORIGIN", "DEST", "BILL_PERIOD", "TRNSPT_MODE"]
    if df["AGENT"].nunique() > 1:
        filters = ["AGENT"] + filters
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
CPKG_COLOR = "#1D4E89"


def _flip(state_key):
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def agent_chart(in_table, agents, key):
    """'View' button under the agent table -> share-% bars and CPKG bars per agent."""
    state_key = f"{key}_agent_chart"
    showing = st.session_state.get(state_key, False)
    st.button("Hide chart" if showing else "📊 View", key=f"{key}_agent_chart_btn",
              on_click=_flip, args=(state_key,))
    if not showing:
        return

    totals = in_table[["CHR_WT", "TOTAL_FRT"]].sum()
    rows = []
    for a in agents:
        part = in_table[in_table["AGENT"] == a]
        rows.append({
            "Agent": a,
            "Lodgement %": len(part) / len(in_table) * 100 if len(in_table) else 0,
            "Volume %": part["CHR_WT"].sum() / totals["CHR_WT"] * 100 if totals["CHR_WT"] else 0,
            "Cost %": part["TOTAL_FRT"].sum() / totals["TOTAL_FRT"] * 100 if totals["TOTAL_FRT"] else 0,
            "CPKG": _cpkg(part),
        })
    data = pd.DataFrame(rows)
    shares = data.melt(id_vars="Agent", value_vars=list(SHARE_COLORS), var_name="Measure", value_name="Share")

    axis_x = alt.Axis(labelAngle=0, title=None, labelColor="#33415C", domain=False, ticks=False)
    axis_y = dict(grid=True, gridColor="#EEF1F6", domain=False, ticks=False, labelColor="#5B6B82",
                  titleColor="#5B6B82")

    share_chart = (
        alt.Chart(shares)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, stroke="#FFFFFF", strokeWidth=2)
        .encode(
            x=alt.X("Agent:N", sort=agents, axis=axis_x),
            xOffset=alt.XOffset("Measure:N", sort=list(SHARE_COLORS)),
            y=alt.Y("Share:Q", title="Share of total (%)", axis=alt.Axis(**axis_y)),
            color=alt.Color("Measure:N", sort=list(SHARE_COLORS),
                            scale=alt.Scale(domain=list(SHARE_COLORS), range=list(SHARE_COLORS.values())),
                            legend=alt.Legend(orient="top", title=None, labelColor="#33415C")),
            tooltip=["Agent", "Measure", alt.Tooltip("Share:Q", title="Share %", format=".1f")],
        )
        .properties(height=320)
    )

    cpkg_base = alt.Chart(data).encode(
        x=alt.X("Agent:N", sort=agents, axis=axis_x),
        y=alt.Y("CPKG:Q", title="CPKG (₹/kg)", axis=alt.Axis(**axis_y)),
    )
    cpkg_chart = (
        cpkg_base.mark_bar(color=CPKG_COLOR, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=28)
        .encode(tooltip=["Agent", alt.Tooltip("CPKG:Q", format=",.2f")])
        + cpkg_base.mark_text(dy=-8, color="#33415C", fontSize=12).encode(text=alt.Text("CPKG:Q", format=",.2f"))
    ).properties(height=320)

    left, right = st.columns([3, 2])
    with left:
        section("Lodgement · Volume · Cost share by agent")
        st.altair_chart(share_chart, use_container_width=True)
    with right:
        section("CPKG by agent")
        st.altair_chart(cpkg_chart, use_container_width=True)


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
    section("Slab-wise · Console vs Direct")
    mode = filtered["LODGE_MODE"].astype(str).str.upper()
    in_table = filtered[mode.isin(["DIRECT", "CONSOLE"]) & filtered["SLAB"].notna()]
    grand = (len(in_table), in_table["CHR_WT"].sum(), in_table["TOTAL_FRT"].sum())

    def pct(x, total):
        return f"{x / total:.0%}" if total else "–"

    def cells(part):
        n, wt, frt = len(part), part["CHR_WT"].sum(), part["TOTAL_FRT"].sum()
        return [_n(n), pct(n, grand[0]), _n(wt), pct(wt, grand[1]), _n(frt), pct(frt, grand[2]),
                _n(_cpkg(part), 2) if n else '<span class="acl-muted">–</span>']

    headers = ["Lodge mode", "Lodgements", "Lodgement %", "CHR_WT", "Volume %", "TOTAL_FRT", "Cost %", "CPKG"]

    def pivot(first_header, parts):
        """parts: (title, rows of in_table) -> one foldable group each: total on top, Console / Direct underneath."""
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

    other = filtered[~mode.isin(["DIRECT", "CONSOLE"])]
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
        section("Agent-wise · Console vs Direct")
        by_frt = in_table.groupby("AGENT")["TOTAL_FRT"].sum().sort_values(ascending=False).index
        pivot("Agent", [(a, in_table[in_table["AGENT"] == a]) for a in by_frt])
        agent_chart(in_table, list(by_frt), key)

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
    lane_headers = ["Lane (OD)", "AWBs", "CHR_WT", "TOTAL_FRT", "CPKG"]
    left, right = st.columns(2)
    with left:
        section("Top 10 lanes by ↑ CPKG")
        html_table(lane_headers, lane_rows(busy.nlargest(n_red, "CPKG")), tone="red")
    with right:
        section("Top 10 lanes by ↓ CPKG")
        html_table(lane_headers, lane_rows(busy.nsmallest(n_green, "CPKG")), tone="green")
    return filtered
