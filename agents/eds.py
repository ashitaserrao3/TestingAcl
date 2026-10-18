"""
EDS bills (Excel). Invoice no. and origin come from the sheet's title row
("ANNEXURE TO INVOICE No. BOM/455/26-27" -> invoice BOM/455/26-27, origin BOM).
Fallback when that row is missing: file name ORIGIN-xxx-xxx... (first 3 parts = invoice no).
"""

import re

import pandas as pd

from utils.common import awb_text, find_col, find_header_row, frame_from_header, strip_ext, to_date, to_num
from utils.excel_utils import read_raw_any

AGENT = "EDS"
KEY = "eds"
LABEL = "EDS"
DESCRIPTION = "EDS bills (.xlsx) · invoice no. and origin read from the bill's title row"
FILE_TYPES = ["xlsx", "xls"]
OUTPUT_FILE = "EDS_Combined.xlsx"

ADDON_PARTS = ["AWB DO", "A/L CHG", "APT OUT", "APT IN", "SVC CHG"]
EXTRA_COLS = ADDON_PARTS + ["CGST", "SGST", "IGST", "AMOUNT"]

SOURCE = {
    "AWB_DATE": ["DATE"],
    "FLIGHT_NO": ["FLIGHT NO.", "FLIGHT NO"],
    "DEST": ["DSTN"],
    "PKGS": ["PCS"],
    "CHR_WT": ["CWGT KGS.", "CWGT KGS"],
    "RATE": ["RATE"],
    "BASIC_FRT": ["FREIGHT CHS"],
    "AWB DO": ["AWB DO"],
    "A/L CHG": ["A/L CHG"],
    "APT OUT": ["APT OUT"],
    "APT IN": ["APT IN"],
    "SVC CHG": ["SVC CHG"],
    "CGST": ["CGST 9%", "CGST"],
    "SGST": ["SGST 9%", "SGST"],
    "IGST": ["IGST 18%", "IGST"],
    "AMOUNT": ["AMOUNT"],
}


_INVOICE = re.compile(r"INVOICE\s*NO\.?\s*[:\-]*\s*([A-Z]{3}\s*[/\-][^\s,]+)", re.I)


def invoice_from_sheet(raw, header_row):
    """'ANNEXURE TO INVOICE No. BOM/455/26-27 Date:-...' above the header -> 'BOM/455/26-27'."""
    for r in range(header_row):
        for v in raw.iloc[r].dropna():
            m = _INVOICE.search(str(v))
            if m:
                return re.sub(r"\s+", "", m.group(1)).upper()
    return None


def invoice_from_name(name):
    """'BOM-455-SEP2ND-ALLCARGO.xlsx' -> ('BOM-455-SEP2ND', 'BOM'); (None, None) if the name isn't like that."""
    parts = [p.strip() for p in strip_ext(name).split("-")]
    if len(parts) >= 2 and re.fullmatch(r"[A-Za-z]{3}", parts[0]):
        return "-".join(parts[:3]), parts[0].upper()
    return None, None


def parse(data, name, log):
    raw, _, _ = read_raw_any(data, name)

    # header used to be assumed on row 3; now found by looking for "AWB NO"
    header_row = find_header_row(raw, lambda cells: any(c.replace(".", "").strip() == "AWB NO" for c in cells))
    if header_row is None:
        raise ValueError("header row (AWB NO) not found")
    df = frame_from_header(raw, header_row)

    awb_col = find_col(df, ["AWB NO.", "AWB NO"], allow_partial=False)
    df = df[df[awb_col].notna()]
    df = df[~df[awb_col].astype(str).str.contains("Airline|Total", case=False, na=False)]

    out = pd.DataFrame(index=df.index)
    out["AWB_NO"] = df[awb_col].map(awb_text).astype("string")

    missing = []
    for target, cands in SOURCE.items():
        src = find_col(df, cands, allow_partial=False)
        if src is None:
            missing.append(cands[0])
            out[target] = pd.NA
        else:
            out[target] = df[src]
    if missing:
        log("warning", f"{name}: columns not found (left blank): {', '.join(missing)}")

    for col in ["PKGS", "CHR_WT", "RATE", "BASIC_FRT"] + EXTRA_COLS:
        out[col] = to_num(out[col], fill=0 if col in ADDON_PARTS else None)

    out["ADDON_CHR"] = out[ADDON_PARTS].sum(axis=1)
    out["TOTAL_FRT"] = out["BASIC_FRT"] + out["ADDON_CHR"]
    out["AWB_DATE"] = to_date(out["AWB_DATE"], dayfirst=True)

    invoice = invoice_from_sheet(raw, header_row)
    if invoice:
        origin = invoice[:3]
    else:
        invoice, origin = invoice_from_name(name)
        if invoice:
            log("info", f"{name}: invoice no. not found in the sheet – taken from the file name")
        else:
            invoice = strip_ext(name)
            log("warning", f"{name}: invoice no. / origin not found in the sheet or the file name "
                           "– origin left blank (see DATA_ISSUE)")
    out["INVOICE_NO"] = invoice
    out["ORIGIN"] = origin
    out["LODGE_MODE"] = out["AWB_NO"].str.contains("-", regex=False).map({True: "Direct", False: "Console"})
    out["TRNSPT_MODE"] = "AIR"
    return out
