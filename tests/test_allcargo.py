import os
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import allcargo  # noqa: E402

HEADER = ["ORG", "DEST", "Airline", "Flight", "Commodity", "N Rate", "Q45", "Q100", "Q250", "Q300", "Q500", "Q1000",
          "Disc/Kg.", "Disc%", "Base+100 Rate", "Terminal&Surcharges", "Master+100", "Console Rate"]


def make_quote(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for line in ("ALLCARGO LOGISTICS LIMITED", "Rate Quotation", "W.E.F. 01-10-2026", "Quotaion Details"):
        ws.append([line])
    ws.append(HEADER)
    for o, d, a, flight, ts, note in rows:
        ws.append([o, d, a, flight, "GENERAL ", 98, 75, 65, None, None, None, None, note, "14%", 55.9, ts, None, None])
    wb.save(path)


def flight(o, d, airline, no):
    return {"Origin": o, "Destination": d, "Airline": airline, "FlightNo": no}


def test_terminal_surcharge_prefers_the_flights_own_row(tmp_path):
    path = tmp_path / "ALLCARGO.xlsx"
    make_quote(path, [
        ("DEL", "CJB", "Air India", "AI 1721", 31.65, None),
        ("DEL", "CJB", "Air India", "ALL", 30.00, None),
        ("DEL", "CJB", "Indigo", "6E 0496", 25.00, None),
        ("DEL", "CJB", "Indigo", "ALL", 23.50, None),
        ("BOM", "DEL", "AKASA", "QP 1109", None, "Prime Flights, SSP & Console Rate as per attached special rates"),
        ("BOM", "DEL", "AKASA", "ALL", 19.00, None),
        ("DEL", "TRV", "STAR AIR", "ALL", 12.00, None),
    ])
    assert allcargo.is_quote(path)
    q = allcargo.read_quote(path)
    assert q["wef"] == "01-10-2026"
    ts = allcargo.terminal_surcharge
    assert ts(q, flight("DEL", "CJB", "AIRINDIA", "AI1721"), "PRIME") == (31.65, "AI1721")
    assert ts(q, flight("DEL", "CJB", "AIRINDIA", "AI1753"), "GCR") == (30.00, "ALL")
    assert ts(q, flight("DEL", "CJB", "INDIGO", "6E496"), "GCR") == (25.00, "6E496")  # '6E 0496' in the sheet
    assert ts(q, flight("BOM", "DEL", "AKASA", "QP1109"), "PRIME") == (19.00, "ALL")  # own row has no number
    assert ts(q, flight("DEL", "TVM", "STARAIR", "S5101"), "GCR") == (12.00, "ALL")   # TRV in the sheet
    assert ts(q, flight("DEL", "BOM", "INDIGO", "6E1"), "GCR") == (None, None)
    assert ts(None, flight("DEL", "CJB", "INDIGO", "6E1"), "GCR") == (None, None)


def test_special_rate_by_product_or_all():
    special = {"rows": {("AMD", "CCU", "AKASA", "PRIME"): {"ssp": 30.0, "console": 50.0},
                        ("BLR", "CCU", "AKASA", "GCR"): {"ssp": 20.0, "console": 42.0},
                        ("AMD", "PNQ", "AKASA", "ALL"): {"ssp": 29.0, "console": 49.0}}}
    sr = allcargo.special_rate
    assert sr(special, flight("AMD", "CCU", "AKASA", "QP1925"), "PRIME")[0]["ssp"] == 30.0
    assert sr(special, flight("AMD", "CCU", "AKASA", "QP1"), "GCR") == (None, None)  # Prime-only route
    assert sr(special, flight("BLR", "CCU", "AKASA", "QP1509"), "GCR")[0]["ssp"] == 20.0
    assert sr(special, flight("AMD", "PNQ", "AKASA", "QP7"), "GCR")[1] == "ALL"
    assert sr(special, flight("AMD", "CCU", "INDIGO", "6E1"), "PRIME") == (None, None)


def test_airline_tariffs_are_not_taken_for_the_quote(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append([" Common User Terminal Charges (16-Apr-2026)"])  # as in SpiceJet's CUT Charges sheet
    wb.save(tmp_path / "sg.xlsx")
    assert not allcargo.is_quote(tmp_path / "sg.xlsx")


def test_missing_route_is_worked_out_from_origin_and_destination_parts(tmp_path):
    # T&S = origin part + destination part: DEL is 4.60 above AYJ, BOM's destination part is 15.36 from AYJ
    path = tmp_path / "ALLCARGO.xlsx"
    make_quote(path, [
        ("AYJ", "BOM", "AKASA", "ALL", 15.36, None),
        ("AYJ", "CCU", "AKASA", "ALL", 13.60, None),
        ("DEL", "CCU", "AKASA", "ALL", 18.20, None),
        ("DEL", "BOM", "AKASA", "GCR", None, "SSP & Console Rate as per attached special rates"),
    ])
    q = allcargo.read_quote(path)
    assert allcargo.terminal_surcharge(q, flight("DEL", "BOM", "AKASA", "QP1119"), "GCR") == (19.96, "DERIVED")
    assert allcargo.terminal_surcharge(q, flight("DEL", "CCU", "AKASA", "QP1"), "GCR") == (18.20, "ALL")
    assert allcargo.terminal_surcharge(q, flight("DEL", "GOI", "AKASA", "QP2"), "GCR") == (None, None)
