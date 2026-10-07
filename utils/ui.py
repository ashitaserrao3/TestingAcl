"""
Look & feel helpers: global CSS, header, page titles, chips, tables.
Colours come from .streamlit/config.toml; this file only adds polish.
"""

import html

import streamlit as st

PLANE = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5'
         'S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/></svg>')
NAVY = "#0B2545"
RED = "#C8102E"

CSS = """
<style>
/* Modern light: white surfaces, soft shadows, ACL red + navy accents */
:root {
  --acl-bg: #F5F7FB; --acl-surface: #FFFFFF; --acl-ink: #0F1B33; --acl-ink-2: #334155;
  --acl-muted: #64748B; --acl-faint: #94A3B8; --acl-line: #E5E9F0; --acl-line-2: #EEF2F7;
  --acl-navy: #0B2545; --acl-blue: #1D4E89; --acl-red: #C8102E; --acl-red-soft: #FDECEE;
  --acl-green: #1E8449; --acl-amber: #D98E04;
  --acl-sky: #CDE7FA; --acl-sky-2: #B9DDF7; --acl-sky-line: #A9D3F2;
  --acl-shadow: 0 1px 2px rgba(15,27,51,.04), 0 4px 16px rgba(15,27,51,.06);
  --acl-shadow-lg: 0 2px 4px rgba(15,27,51,.04), 0 12px 32px rgba(15,27,51,.08);
}

/* ---------- layout ---------- */
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1400px; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAlert"] { border-radius: 12px; }

/* ---------- top brand bar ---------- */
.acl-topbar {
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  background: var(--acl-surface); color: var(--acl-ink); border: 1px solid var(--acl-line);
  border-radius: 16px; padding: 14px 20px; margin-bottom: 1.6rem; box-shadow: var(--acl-shadow);
}
.acl-brand { display: flex; align-items: center; gap: 14px; }
.acl-logo {
  width: 42px; height: 42px; border-radius: 12px; background: var(--acl-red);
  display: flex; align-items: center; justify-content: center; font-size: 22px; flex: none;
  box-shadow: 0 4px 12px rgba(200,16,46,.28);
}
.acl-brand-name { font-size: 1.25rem; font-weight: 700; letter-spacing: -.01em; line-height: 1.1; color: var(--acl-navy); }
.acl-brand-sub  { font-size: .8rem; color: var(--acl-muted); margin-top: 3px; }
.acl-topbar-right { font-size: .8rem; font-weight: 500; color: var(--acl-ink-2); background: var(--acl-bg);
  border: 1px solid var(--acl-line); border-radius: 999px; padding: 6px 14px; white-space: nowrap; }

/* ---------- page title ---------- */
.acl-page-title { margin: .2rem 0 1.1rem; }
.acl-page-title h2 { margin: 0; padding: 0; font-size: 1.75rem; font-weight: 700; letter-spacing: -.02em;
  color: var(--acl-ink); }
.acl-page-title p  { margin: .3rem 0 0; color: var(--acl-muted); font-size: .92rem; }

/* ---------- chips ---------- */
.acl-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: .2rem 0 .9rem; }
.acl-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px;
  font-size: .8rem; font-weight: 600; border: 1px solid var(--acl-line); background: #fff; color: var(--acl-ink-2);
}
.acl-chip.ok   { background: #E9F7EF; border-color: #C6E9D3; color: #17663A; }
.acl-chip.warn { background: #FFF7E6; border-color: #F7E1AE; color: #8A5A00; }
.acl-chip.bad  { background: var(--acl-red-soft); border-color: #F6C3CA; color: #A0102A; }
.acl-chip.info { background: #EDF3FC; border-color: #CFDDF3; color: var(--acl-blue); }

/* ---------- section label ---------- */
.acl-section { display: flex; align-items: center; gap: 8px; font-size: .8rem; font-weight: 700;
  letter-spacing: .06em; text-transform: uppercase; color: var(--acl-ink-2); margin: 1.4rem 0 .6rem; }
.acl-section::before { content: ""; width: 4px; height: 14px; border-radius: 2px; background: var(--acl-red); flex: none; }

/* ---------- metric cards ---------- */
[data-testid="stMetric"] {
  background: var(--acl-surface); border: 1px solid var(--acl-line); border-left: 4px solid var(--acl-navy);
  border-radius: 14px; padding: 16px 18px; box-shadow: var(--acl-shadow);
}
[data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stMetric"] { border-left-color: var(--acl-red); }
[data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stMetric"] { border-left-color: var(--acl-blue); }
[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetric"] { border-left-color: var(--acl-green); }
[data-testid="stMetricLabel"] p { font-size: .72rem !important; color: var(--acl-muted); font-weight: 600;
  text-transform: uppercase; letter-spacing: .06em; }
[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700; color: var(--acl-ink); letter-spacing: -.02em; }

/* ---------- tables ---------- */
.acl-table { width: 100%; border-collapse: separate !important; border-spacing: 0; background: #fff;
  border: 1px solid var(--acl-line); border-top: 3px solid var(--acl-blue); border-radius: 14px; overflow: hidden;
  font-size: .9rem; box-shadow: var(--acl-shadow); }
.acl-table th { background: #F8FAFC; color: var(--acl-muted); font-weight: 700; text-align: right;
  padding: 11px 14px; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em;
  border-bottom: 1px solid var(--acl-line); }
.acl-table th:first-child, .acl-table td:first-child { text-align: left; }
.acl-table td { padding: 11px 14px; text-align: right; border-top: 1px solid var(--acl-line-2); color: var(--acl-ink);
  font-variant-numeric: tabular-nums; }
.acl-table tbody tr:hover td { background: #F7F9FD; }
.acl-table tr.total td { font-weight: 700; background: #F8FAFC; border-top: 1.5px solid #D5DCE6; }
.acl-table tr.sub td { font-weight: 600; background: #FBFCFE; }
.acl-table tr.detail td { color: var(--acl-ink-2); }
.acl-table .grp { border-left: 1px solid var(--acl-line-2); }
.acl-table .txt { text-align: left; }
.acl-table.red { border-color: #F2C9CF; border-top-color: var(--acl-red); }
.acl-table.red th { background: #FFF5F6; color: #9B1C2C; border-bottom-color: #F2C9CF; }
.acl-table.red td:last-child b { color: var(--acl-red); }
.acl-table.green { border-color: #C3E6D0; border-top-color: var(--acl-green); }
.acl-table.green th { background: #F2FAF5; color: #1E6B3A; border-bottom-color: #C3E6D0; }
.acl-table.green td:last-child b { color: var(--acl-green); }
.acl-fold { cursor: pointer; user-select: none; display: inline-flex; align-items: center; gap: 6px; }
.acl-fold input { display: none; }
.acl-caret::before { content: "⊞"; display: inline-block; width: 1.1em; font-size: 1.1em; color: var(--acl-faint); }
.acl-fold-grp:has(.acl-fold input:checked) .acl-caret::before { content: "⊟"; color: var(--acl-red); }
.acl-fold-grp tr.detail { display: none; }  /* collapsed until clicked */
.acl-fold-grp:has(.acl-fold input:checked) tr.detail { display: table-row; }
.acl-muted { color: var(--acl-faint); }

/* ---------- cards / uploader ---------- */
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {
  background: var(--acl-surface); border-color: var(--acl-line) !important; border-radius: 16px !important;
  box-shadow: var(--acl-shadow); }
[data-testid="stFileUploaderDropzone"] { background: #F8FAFC; border: 1.5px dashed #CBD5E1; border-radius: 12px; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--acl-red); background: #FFF8F9; }

/* ---------- buttons ---------- */
.stButton button, .stDownloadButton button { border-radius: 10px; font-weight: 600; }
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
  box-shadow: 0 4px 14px rgba(200,16,46,.25); border: none; }
.stButton button[kind="secondary"], .stDownloadButton button[kind="secondary"] {
  background: #fff; border: 1px solid var(--acl-line); box-shadow: var(--acl-shadow); }

/* ---------- tabs (pill style) ---------- */
.stTabs [role="tablist"] { gap: 4px; background: #EBEFF5; padding: 4px; border-radius: 12px;
  border: none; width: fit-content; max-width: 100%; }
.stTabs [data-testid="stTab"] { padding: 7px 16px; font-weight: 600; border-radius: 9px; color: var(--acl-muted);
  height: auto; border: none; }
.stTabs [data-testid="stTab"]:hover { color: var(--acl-ink); }
.stTabs [data-testid="stTab"][aria-selected="true"] { background: #fff; color: var(--acl-red);
  box-shadow: 0 1px 3px rgba(15,27,51,.12); }
.stTabs [data-testid="stTab"] p { color: inherit; font-weight: inherit; }
.stTabs [role="tablist"]::after, .stTabs .react-aria-SelectionIndicator { display: none; }  /* default underline */

/* ---------- sidebar (light sky blue) ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #DCEFFC 0%, var(--acl-sky) 100%);
  border-right: 1px solid var(--acl-sky-line); }
[data-testid="stSidebar"] .acl-side-brand { display: flex; align-items: center; gap: 10px; margin: -.4rem 0 1.1rem; }
[data-testid="stSidebar"] .acl-side-brand .acl-logo { width: 34px; height: 34px; font-size: 18px; border-radius: 10px; }
[data-testid="stSidebar"] .acl-side-name { font-weight: 700; font-size: 1.05rem; color: var(--acl-navy); }
[data-testid="stSidebar"] .acl-user {
  background: rgba(255,255,255,.75); border: 1px solid var(--acl-sky-line); border-radius: 12px;
  padding: 10px 12px; margin-bottom: 1.1rem; font-size: .85rem; color: var(--acl-muted); }
[data-testid="stSidebar"] .acl-user b { display: block; font-size: .95rem; color: var(--acl-ink); }
[data-testid="stSidebar"] .acl-user span { font-size: .75rem; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 2px; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding: 8px 12px; border-radius: 10px; width: 100%; margin: 0; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: rgba(255,255,255,.6); }
[data-testid="stSidebar"] [role="radiogroup"] label p { color: var(--acl-ink-2); font-weight: 500; }
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {
  background: #fff; box-shadow: inset 3px 0 0 var(--acl-red), 0 1px 3px rgba(15,27,51,.08); }
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p { color: var(--acl-red); font-weight: 700; }
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) {
  display: none; }  /* hide radio dot – rows look like a menu */
.acl-side-label { font-size: .7rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
  color: #4A7398; margin: .4rem 0 .35rem; }
[data-testid="stSidebar"] hr { border-color: var(--acl-sky-line); }

/* ---------- login ---------- */
.acl-login-head { text-align: center; margin: 4vh 0 1.4rem; }
.acl-login-head .acl-logo { width: 58px; height: 58px; font-size: 28px; border-radius: 16px; margin: 0 auto 14px; }
.acl-login-head h1 { font-size: 1.75rem; margin: 0; padding: 0; color: var(--acl-ink); letter-spacing: -.02em; }
.acl-login-head p { color: var(--acl-muted); margin: .35rem 0 0; font-size: .92rem; }
[data-testid="stForm"] { background: #fff; border: 1px solid var(--acl-line); border-radius: 18px;
  padding: 1.6rem 1.6rem 1.2rem; box-shadow: var(--acl-shadow-lg); }
[data-testid="stForm"] [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]),
[data-testid="stForm"] [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]) > div,
[data-testid="stForm"] [data-testid="stFormSubmitButton"] { width: 100% !important; }
[data-testid="stFormSubmitButton"] button {
  width: 100% !important; justify-content: center; background: var(--acl-red); color: #fff; border: none;
  font-weight: 600; padding: .6rem 0; border-radius: 10px; box-shadow: 0 4px 14px rgba(200,16,46,.25); }
[data-testid="stFormSubmitButton"] button:hover { background: #A50D26; color: #fff; }
.acl-logo svg { width: 58%; height: 58%; fill: #fff; }
.acl-foot { text-align: center; color: var(--acl-faint); font-size: .78rem; margin-top: 1.2rem; }

/* ---------- mobile ---------- */
@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 1rem; }
  .acl-topbar { padding: 12px 14px; }
  .acl-topbar-right { display: none; }
  .acl-brand-name { font-size: 1.1rem; }
  [data-testid="stMetricValue"] { font-size: 1.3rem !important; }
  .acl-table { font-size: .8rem; }
  .acl-table th, .acl-table td { padding: 8px 8px; }
  .stTabs [data-baseweb="tab-list"] { width: auto; }
}
</style>
"""


def apply_css():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x):
    return html.escape(str(x))


def topbar(right_text=""):
    st.markdown(
        f"""<div class="acl-topbar">
              <div class="acl-brand">
                <div class="acl-logo">{PLANE}</div>
                <div><div class="acl-brand-name">ACL Air Cargo Bills</div>
                     <div class="acl-brand-sub">Freight bill processing &amp; CPKG analysis</div></div>
              </div>
              <div class="acl-topbar-right">{esc(right_text)}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def login_header():
    st.markdown(
        f"""<div class="acl-login-head">
             <div class="acl-logo">{PLANE}</div>
             <h1>ACL Air Cargo Bills</h1>
             <p>Sign in to process agent freight bills</p>
           </div>""",
        unsafe_allow_html=True,
    )


def login_footer():
    st.markdown('<div class="acl-foot">Trouble signing in? Contact the Tariff &amp; Yield team.</div>',
                unsafe_allow_html=True)


def sidebar_brand(name, username):
    st.sidebar.markdown(
        f"""<div class="acl-side-brand"><div class="acl-logo">{PLANE}</div>
              <div class="acl-side-name">ACL Air Cargo Bills</div></div>
            <div class="acl-user"><span>Signed in as</span><b>{esc(name)}</b><span>@{esc(username)}</span></div>""",
        unsafe_allow_html=True,
    )


def side_label(text):
    st.sidebar.markdown(f'<div class="acl-side-label">{esc(text)}</div>', unsafe_allow_html=True)


def page_title(title, subtitle=""):
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    st.markdown(f'<div class="acl-page-title"><h2>{esc(title)}</h2>{sub}</div>', unsafe_allow_html=True)


def section(text):
    st.markdown(f'<div class="acl-section">{esc(text)}</div>', unsafe_allow_html=True)


def chips(items):
    """items: list of (text, kind) where kind in ok / warn / bad / info / ''"""
    inner = "".join(f'<span class="acl-chip {k}">{esc(t)}</span>' for t, k in items if t)
    st.markdown(f'<div class="acl-chips">{inner}</div>', unsafe_allow_html=True)


def _cell_cls(group_starts, text_cols):
    def cls(i):
        names = " ".join(n for n, on in (("grp", i in group_starts), ("txt", i in text_cols)) if on)
        return f' class="{names}"' if names else ""
    return cls


def _tr(cells, cls, row_cls=""):
    attr = f' class="{row_cls}"' if row_cls else ""
    return f"<tr{attr}>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(cells)) + "</tr>"


def html_table(headers, rows, total_row=None, group_starts=(), text_cols=(0,), fold_groups=None, tone=""):
    """Simple styled table. group_starts: column indexes that get a left divider.
    tone: "red" / "green" tints the header and bold values.
    text_cols: left-aligned (non-number) columns.
    fold_groups: list of (summary_row, detail_rows) shown instead of `rows`; the
    first cell of each summary row becomes a ⊞/⊟ toggle; detail rows start hidden."""
    cls = _cell_cls(group_starts, text_cols)
    head = "".join(f"<th{cls(i)}>{h}</th>" for i, h in enumerate(headers))
    if fold_groups is None:
        body = "<tbody>" + "".join(_tr(r, cls) for r in rows)
        body += (_tr(total_row, cls, "total") if total_row else "") + "</tbody>"
    else:
        body = ""
        for summary, details in fold_groups:
            toggle = f'<label class="acl-fold"><input type="checkbox"><span class="acl-caret"></span>{summary[0]}</label>'
            body += ('<tbody class="acl-fold-grp">' + _tr([toggle] + list(summary[1:]), cls, "sub")
                     + "".join(_tr(r, cls, "detail") for r in details) + "</tbody>")
        if total_row:
            body += "<tbody>" + _tr(total_row, cls, "total") + "</tbody>"
    st.markdown(f'<table class="acl-table {tone}"><thead><tr>{head}</tr></thead>{body}</table>',
                unsafe_allow_html=True)
