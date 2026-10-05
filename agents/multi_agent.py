"""Process bills from several agents together into one dataset/workbook."""

import hashlib

import streamlit as st

from agents import AGENT_MODULES
from utils.activity_log import log_event
from utils.exporter import export_multi
from utils.page import files_signature, process_agent_files, show_results
from utils.schema import combine
from utils.ui import page_title

KEY = "multi"


def run():
    page_title("All agents", "Upload bills for any number of agents, then process them together into one workbook.")

    uploads = {}
    with st.container(border=True):
        cols = st.columns(2)
        for i, mod in enumerate(AGENT_MODULES):
            with cols[i % 2]:
                uploads[mod.KEY] = st.file_uploader(
                    f"{mod.LABEL}  ·  {', '.join('.' + t for t in mod.FILE_TYPES)}",
                    type=mod.FILE_TYPES,
                    accept_multiple_files=True,
                    key=f"multi_{mod.KEY}",
                )

    chosen = [(m, uploads[m.KEY]) for m in AGENT_MODULES if uploads[m.KEY]]
    if not chosen:
        st.session_state.pop(KEY, None)
        st.caption("Add files for at least one agent to continue.")
        return

    n_files = sum(len(f) for _, f in chosen)
    sig = hashlib.md5("|".join(f"{m.KEY}:{files_signature(f)}" for m, f in chosen).encode()).hexdigest()
    cached = st.session_state.get(KEY)

    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    c1.markdown(f"**{n_files} file(s)** ready from **{len(chosen)} agent(s)**: "
                + ", ".join(m.LABEL for m, _ in chosen))
    clicked = c2.button("Process all", type="primary", width="stretch")

    if clicked:
        logs, frames = [], []
        progress = st.progress(0.0, text="Starting…")
        for i, (mod, files) in enumerate(chosen):
            progress.progress(i / len(chosen), text=f"Processing {mod.LABEL}…")
            log = lambda lvl, m, label=mod.LABEL: logs.append((lvl, f"[{label}] {m}"))
            frames.append(process_agent_files(mod, files, log))
        progress.empty()
        df = combine(frames)
        cached = {"sig": sig, "df": df, "logs": logs}
        st.session_state[KEY] = cached
        log_event("PROCESS", "Multi-Agent: " + "; ".join(f"{m.LABEL} {len(f)} file(s)" for m, f in chosen)
                  + f" – {len(df)} rows")

    if not cached:
        return
    if cached["sig"] != sig:
        st.info("Files changed – click **Process all** to refresh the results.")
        return

    df = cached["df"]
    if df.empty:
        st.warning("No valid rows found in these files.")
        return

    show_results(
        df, cached["logs"], KEY, "MultiAgent_Combined.xlsx",
        lambda d: export_multi(d).getvalue(), cached, n_files=n_files,
    )
