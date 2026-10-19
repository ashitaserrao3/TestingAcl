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


def test_rows_are_matched_by_flight_number_first(tmp_path):
    path = tmp_path / "ALLCARGO.xlsx"
    make_quote(path, [
        ("DEL", "CJB", "Air India", "AI 1721", 31.65, None),
        ("DEL", "CJB", "Air India", "ALL", 30.00, None),
        ("DEL", "CJB", "Indigo", "6E 0496", 25.00, None),
        ("DEL", "CJB", "Indigo", "ALL", 23.50, None),
        ("DEL", "TRV", "STAR AIR", "ALL", 12.00, None),
    ])
    assert allcargo.is_quote(path)
    q = allcargo.read_quote(path)
    assert q["wef"] == "01-10-2026"
    row = allcargo.quote_row
    assert row(q, flight("DEL", "CJB", "AIRINDIA", "AI1721"), "PRIME")[1] == "AI1721"
    assert row(q, flight("DEL", "CJB", "AIRINDIA", "AI1753"), "GCR")[0]["ts"] == 30.00
    assert row(q, flight("DEL", "CJB", "INDIGO", "6E496"), "GCR")[0]["ts"] == 25.00  # '6E 0496' in the sheet
    assert row(q, flight("DEL", "TVM", "STARAIR", "S5101"), "GCR")[0]["ts"] == 12.00  # TRV in the sheet
    assert row(q, flight("DEL", "BOM", "INDIGO", "6E1"), "GCR") == (None, None)
    assert row(None, flight("DEL", "CJB", "INDIGO", "6E1"), "GCR") == (None, None)


def test_special_rate_for_flights_whose_row_points_to_the_special_rates(tmp_path):
    path = tmp_path / "ALLCARGO.xlsx"
    prime = "Prime Flights, SSP & Console Rate as per attached special rates"
    make_quote(path, [
        ("BOM", "DEL", "AKASA", "QP 1109", None, prime),
        ("BOM", "DEL", "AKASA", "ALL", 19.71, None),
        ("DEL", "BOM", "AKASA", "QP 1119", None, "SSP & Console Rate as per attached special rates"),
        ("DEL", "BOM", "AKASA", "GCR", None, "SSP & Console Rate as per attached special rates"),
        ("AMD", "PNQ", "AKASA", "GCR", None, prime),
    ])
    q = allcargo.read_quote(path)
    special = {"rows": {("BOM", "DEL", "AKASA", "PRIME"): {"ssp": 26.0, "console": 46.0},
                        ("DEL", "BOM", "AKASA", "PRIME"): {"ssp": 17.0, "console": 47.0},
                        ("DEL", "BOM", "AKASA", "GCR"): {"ssp": 16.0, "console": 37.0},
                        ("AMD", "PNQ", "AKASA", "ALL"): {"ssp": 29.0, "console": 49.0}}}
    sr = allcargo.special_rate
    assert sr(q, special, flight("BOM", "DEL", "AKASA", "QP1109"), "PRIME")[1] == "PRIME"
    # the tariff says GCR and the special sheet has only a Prime rate: the tariff wins, no special rate,
    # and the flight takes the Terminal & Surcharges of the route's ALL row
    assert sr(q, special, flight("BOM", "DEL", "AKASA", "QP1109"), "GCR") == (None, None)
    assert allcargo.quote_row(q, flight("BOM", "DEL", "AKASA", "QP1109"), "GCR", with_number=True)[0]["ts"] == 19.71
    assert sr(q, special, flight("BOM", "DEL", "AKASA", "QP1127"), "GCR") == (None, None)   # ALL row has a T&S
    assert sr(q, special, flight("DEL", "BOM", "AKASA", "QP1119"), "GCR")[1] == "GCR"
    assert sr(q, special, flight("DEL", "BOM", "AKASA", "QP1119"), "PRIME")[1] == "PRIME"
    assert sr(q, special, flight("DEL", "BOM", "AKASA", "QP1110"), "GCR")[0]["ssp"] == 16.0  # the GCR row
    assert sr(q, special, flight("AMD", "PNQ", "AKASA", "QP1911"), "GCR")[1] == "ALL"
    assert sr(q, None, flight("DEL", "BOM", "AKASA", "QP1119"), "GCR") == (None, None)


def test_airline_tariffs_are_not_taken_for_the_quote(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append([" Common User Terminal Charges (16-Apr-2026)"])  # as in SpiceJet's CUT Charges sheet
    wb.save(tmp_path / "sg.xlsx")
    assert not allcargo.is_quote(tmp_path / "sg.xlsx")

