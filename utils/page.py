"""
Shared Streamlit page for every agent:
upload -> parse each file -> standardize -> dashboard -> table -> download.

Results are cached per agent, keyed on the exact files uploaded, so
uploading a different set of files always re-processes (no stale data).
"""

import hashlib

import pandas as pd
import streamlit as st

from utils.activity_log import log_event
from utils.dashboard import show_dashboard
from utils.ui import chips, page_title
from utils.common import get_airline
from utils.excel_utils import formula_cells_without_values
from utils.exporter import export_excel
from utils.schema import standardize


def files_signature(files):
    h = hashlib.md5()
    for f in files:
        h.update(f.name.encode())
        h.update(f.getvalue())
    return h.hexdigest()


BLANK_CHECK = {"AWB_DATE": "date", "DEST": "destination", "CHR_WT": "weight", "TOTAL_FRT": "total"}


def report_blanks(df, f, log, skip_sheet=None):
    """Tell the user exactly which cells came through empty, and why if we can tell."""
    gaps = []
    for col, label in BLANK_CHECK.items():
        if col in df.columns:
            n = int(pd.Series(df[col]).isna().sum())
            if n:
                gaps.append(f"{n} without {label}")
    if gaps:
        log("warning", f"{f.name}: " + ", ".join(gaps) + " (see DATA_ISSUE column)")

    missing = formula_cells_without_values(f.getvalue(), f.name, skip_sheet)
    if missing:
        log("warning", f"{f.name}: {missing} formula cells have no saved value and read as blank – "
                       "open the file in Excel, press Save, and upload it again")


def process_agent_files(agent_module, files, log):
    """Parse + standardize. Pure (no st.* calls) apart from the log callback."""
    frames = []
    for f in files:
        try:
            df = agent_module.parse(f.getvalue(), f.name, log)
        except Exception as e:  # keep going with the other files
            log("error", f"{f.name}: {e}")
            continue
        if df is None or df.empty:
            log("warning", f"{f.name}: no rows found")
            continue
        df["SOURCE_FILE"] = f.name
        log("info", f"{f.name}: {len(df)} rows")
        report_blanks(df, f, log, getattr(agent_module, "should_skip", None))
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True, sort=False)
    out = standardize(raw, agent_module.AGENT, agent_module.EXTRA_COLS)
    report_airlines(out, log)
    return out


def report_airlines(df, log):
    """Per file: how many airlines came from the AWB prefix, and which flight cells were not understood."""
    air = df[df["TRNSPT_MODE"] != "ROAD"]
    for fname, part in air.groupby("SOURCE_FILE"):
        from_flight = part["FLIGHT_NO"].map(get_airline)
        via_awb = int((from_flight.isna() | (from_flight == "Other")).sum()
                      - (part["AIRLINE"].isna() | (part["AIRLINE"] == "Other")).sum())
        if via_awb:
            log("info", f"{fname}: airline for {via_awb} rows taken from the AWB prefix (flight cell empty/unclear)")
        bad = part[part["AIRLINE"].isna() | (part["AIRLINE"] == "Other")]
        if len(bad):
            samples = bad["FLIGHT_NO"].fillna("(empty)").astype(str).unique()[:6]
            log("warning", f"{fname}: airline not recognised for {len(bad)} rows – flight cells: "
                           + ", ".join(samples) + ". Send these to have them added.")


def show_problems(logs):
    """Errors / warnings stay visible above the results."""
    for lvl, m in logs:
        if lvl == "error":
            st.error(m, icon="⛔")
        elif lvl == "warning":
            st.warning(m, icon="⚠️")


def quality_chips(df, logs, n_files=None):
    removed = df.attrs.get("exact_dups_removed", 0)
    dup = int(df["DUP_FLAG"].notna().sum())
    issue = int(df["DATA_ISSUE"].notna().sum())
    errors = sum(1 for lvl, _ in logs if lvl == "error")
    items = [(f"✓ {len(df):,} rows", "ok")]
    if n_files:
        items.append((f"{n_files} file(s)", "info"))
    if df["AGENT"].nunique() > 1:
        items.append((f"{df['AGENT'].nunique()} agents", "info"))
    if removed:
        items.append((f"{removed} exact repeats removed", ""))
    if dup:
        items.append((f"{dup} repeated AWBs", "warn"))
    if issue:
        items.append((f"{issue} data issues", "warn"))
    if errors:
        items.append((f"{errors} file errors", "bad"))
    chips(items)


ISSUE_COLS = ["AGENT", "INVOICE_NO", "AWB_NO", "AWB_DATE", "OD_PAIR", "CHR_WT", "TOTAL_FRT",
              "DUP_FLAG", "DATA_ISSUE", "SOURCE_FILE"]
DATE_CFG = {"AWB_DATE": st.column_config.DateColumn(format="DD-MMM-YYYY")}


NO_DATE = "No AWB date"


def month_filter(df, key):
    """'AWB month' picker. Returns (rows for the chosen month, label)."""
    months = df["AWB_DATE"].dt.to_period("M")
    counts = months.value_counts().sort_index(ascending=False)
    labels = {"All months": f"All months ({len(df):,} AWBs)"}
    for p, n in counts.items():
        labels[str(p)] = f"{p.strftime('%b %Y')} ({n:,} AWBs)"
    n_nodate = int(months.isna().sum())
    if n_nodate:
        labels[NO_DATE] = f"{NO_DATE} ({n_nodate:,})"

    choice = st.selectbox(
        "AWB month", list(labels), format_func=labels.get, key=f"{key}_month",
        help="Show only AWBs dated in this month – dashboard, data, issues and the Excel download all follow it.",
    )
    if choice == "All months":
        return df, None
    if choice == NO_DATE:
        return df[months.isna()], NO_DATE
    return df[months.astype(str) == choice], pd.Period(choice).strftime("%b %Y")


def show_results(df_all, logs, key, file_name, make_excel, cache, n_files=None):
    """Month filter + status chips + download, then tabs: Dashboard / Data / Issues / Log."""
    f_col, _ = st.columns([1, 2])
    with f_col:
        df, month = month_filter(df_all, key)
    if month:
        hidden = len(df_all) - len(df)
        st.caption(f"Showing **{month}** only – {hidden:,} AWB(s) from other months hidden.")

    # Excel follows the month filter; each version is built once and kept
    tag = month or "all"
    xl = cache.setdefault("xlsx_by_month", {})
    if tag not in xl:
        with st.spinner("Preparing Excel…"):
            xl[tag] = make_excel(df)
    out_name = file_name if not month else file_name.replace(".xlsx", f"_{month.replace(' ', '')}.xlsx")

    top_l, top_r = st.columns([3, 1], vertical_alignment="center")
    with top_l:
        quality_chips(df, logs, n_files)
    with top_r:
        st.download_button(
            "⬇  Download Excel",
            data=xl[tag],
            file_name=out_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key}_download",
            type="primary",
            width="stretch",
            on_click=log_event,
            args=("DOWNLOAD", out_name),
        )
    show_problems(logs)

    flagged = df[df["DUP_FLAG"].notna() | df["DATA_ISSUE"].notna()]
    infos = [m for lvl, m in logs if lvl == "info"]
    t_dash, t_data, t_issue, t_log = st.tabs(
        ["📊  Dashboard", "📋  Data", f"⚠️  Issues ({len(flagged)})", "🧾  Processing log"]
    )

    with t_dash:
        show_dashboard(df, key=key, pdf_name=out_name.replace(".xlsx", "_Dashboard.pdf"), month=month)

    with t_data:
        q = st.text_input("Search", placeholder="AWB no, invoice, lane…", key=f"{key}_q",
                          label_visibility="collapsed")
        view = df
        if q:
            mask = pd.Series(False, index=df.index)
            for col in ["AWB_NO", "INVOICE_NO", "OD_PAIR", "FLIGHT_NO", "SOURCE_FILE"]:
                mask |= df[col].astype(str).str.contains(q, case=False, na=False, regex=False)
            view = df[mask]
        st.caption(f"{len(view):,} of {len(df):,} rows")
        st.dataframe(view, width="stretch", height=520, column_config=DATE_CFG)

    with t_issue:
        if flagged.empty:
            st.success("No repeated AWBs or data issues found.", icon="✅")
        else:
            st.caption("DUP_FLAG = same AWB on more than one row (all rows kept). "
                       "DATA_ISSUE = something missing or not matching in the bill.")
            st.dataframe(flagged[ISSUE_COLS], width="stretch", hide_index=True, column_config=DATE_CFG)

    with t_log:
        if not infos:
            st.caption("Nothing to show.")
        for m in infos:
            st.markdown(f"- {m}")


def run_agent_page(agent_module):
    key = f"agent_{agent_module.KEY}"
    types = ", ".join(f".{t}" for t in agent_module.FILE_TYPES)
    page_title(f"{agent_module.LABEL}", getattr(agent_module, "DESCRIPTION", "") or f"Upload {types} bills")

    with st.container(border=True):
        files = st.file_uploader(
            f"Upload {agent_module.LABEL} bills ({types}) – you can select several files",
            type=agent_module.FILE_TYPES,
            accept_multiple_files=True,
            key=f"{key}_upload",
        )

    if not files:
        st.session_state.pop(key, None)
        st.caption("Results appear here once files are uploaded.")
        return

    sig = files_signature(files)
    cached = st.session_state.get(key)

    if not cached or cached["sig"] != sig:
        logs = []
        with st.spinner(f"Reading {len(files)} file(s)…"):
            df = process_agent_files(agent_module, files, lambda lvl, m: logs.append((lvl, m)))
        cached = {"sig": sig, "df": df, "logs": logs}
        st.session_state[key] = cached
        log_event("PROCESS", f"{agent_module.LABEL}: {len(files)} file(s), {len(df)} rows – " + ", ".join(f.name for f in files))

    df = cached["df"]
    if df.empty:
        show_problems(cached["logs"])
        st.warning("No valid rows found in these files.")
        return

    sheet = agent_module.KEY.upper()
    show_results(
        df, cached["logs"], key, agent_module.OUTPUT_FILE,
        lambda d: export_excel(d, sheet_name=sheet).getvalue(), cached, n_files=len(files),
    )
