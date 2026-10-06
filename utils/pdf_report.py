"""
Dashboard -> PDF (A4 landscape) with reportlab.

show_dashboard() collects what it draws into a `report` list of blocks; build_pdf()
turns those blocks into the same tables / chart on paper:
    ("kpis",   [(label, value), ...])
    ("table",  title, headers, rows, total_row)   rows: (kind, cells), kind = "sub" | "detail" | ""
    ("note",   text)
    ("chart",  title, agents, {measure: [share %, ...]}, {measure: [label, ...]})
    ("lanes",  [(title, headers, rows, tone), ...])   four tables in a 2 x 2 grid
"""

import html
import io
import os
import re
from datetime import datetime

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#0B2545")
RED = colors.HexColor("#C8102E")
INK = colors.HexColor("#14213D")
MUTED = colors.HexColor("#5B6B82")
LINE = colors.HexColor("#DDE3EC")
HEAD_BG = colors.HexColor("#F0F3F8")
SUB_BG = colors.HexColor("#F5F7FB")
TONES = {"red": (colors.HexColor("#FDECEE"), colors.HexColor("#9B1C2C")),
         "green": (colors.HexColor("#E8F5EE"), colors.HexColor("#1E6B3A")),
         "": (HEAD_BG, colors.HexColor("#33415C"))}

# DejaVu has the ₹ sign (packages.txt installs it on Streamlit Cloud); without it fall back to "Rs"
_DEJAVU = "/usr/share/fonts/truetype/dejavu/"
if os.path.exists(_DEJAVU + "DejaVuSans.ttf") and os.path.exists(_DEJAVU + "DejaVuSans-Bold.ttf"):
    pdfmetrics.registerFont(TTFont("ACL", _DEJAVU + "DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("ACL-Bold", _DEJAVU + "DejaVuSans-Bold.ttf"))
    FONT, BOLD, RUPEE = "ACL", "ACL-Bold", "₹"
else:
    FONT, BOLD, RUPEE = "Helvetica", "Helvetica-Bold", "Rs "


def _plain(x):
    """Cell text from the dashboard's HTML cells: drop tags, unescape, swap ₹ if the font lacks it."""
    text = html.unescape(re.sub(r"<[^>]+>", "", str(x)))
    return text.replace("₹", RUPEE) if RUPEE != "₹" else text


def _style(name, size, color=INK, bold=False, **kw):
    return ParagraphStyle(name, fontName=BOLD if bold else FONT, fontSize=size, leading=size * 1.3,
                          textColor=color, **kw)


SECTION = _style("section", 8.5, MUTED, bold=True, spaceBefore=10, spaceAfter=4)
NOTE = _style("note", 7.5, MUTED)


def _section(title):
    return Paragraph(_plain(title).upper(), SECTION)


def _table(headers, rows, total=None, tone="", font_size=7.5, col_widths=None, text_cols=1):
    """rows: list of (kind, cells). The first `text_cols` columns are left-aligned, the rest right-aligned."""
    data = [[_plain(h).upper() for h in headers]]
    kinds = []
    for kind, cells in rows:
        cells = [_plain(c) for c in cells]
        if kind == "detail":
            cells[0] = "    " + cells[0]
        data.append(cells)
        kinds.append(kind)
    if total:
        data.append([_plain(c) for c in total])
        kinds.append("total")

    head_bg, head_ink = TONES[tone]
    style = [
        ("FONT", (0, 0), (-1, -1), FONT, font_size),
        ("FONT", (0, 0), (-1, 0), BOLD, font_size - 0.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), head_ink),
        ("BACKGROUND", (0, 0), (-1, 0), head_bg),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ALIGN", (text_cols, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, kind in enumerate(kinds, start=1):
        if kind == "sub":
            style += [("BACKGROUND", (0, i), (-1, i), SUB_BG), ("FONT", (0, i), (-1, i), BOLD, font_size)]
        elif kind == "total":
            style += [("FONT", (0, i), (-1, i), BOLD, font_size), ("LINEABOVE", (0, i), (-1, i), 0.8, MUTED)]
        elif kind == "detail":
            style += [("TEXTCOLOR", (0, i), (-1, i), MUTED)]
    if tone in ("red", "green"):  # CPKG column in the tone colour, like the app
        style += [("TEXTCOLOR", (-1, 1), (-1, -1), head_ink), ("FONT", (-1, 1), (-1, -1), BOLD, font_size),
                  ("FONT", (0, 1), (0, -1), BOLD, font_size)]
    t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle(style))
    return t


def _kpis(items, width):
    cells = [[Paragraph(_plain(label), _style("kl", 7.5, MUTED)) for label, _ in items],
             [Paragraph(_plain(value), _style("kv", 15, INK, bold=True)) for _, value in items]]
    t = Table(cells, colWidths=[width / len(items)] * len(items), hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _chart(agents, shares, labels, colours, width):
    """Grouped bars: one group per agent, one bar per measure, % and actual value above each bar."""
    height = 62 * mm
    d = Drawing(width, height)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 28, 28, width - 40, height - 52
    measures = list(shares)
    bc.data = [shares[m] for m in measures]
    top = max([v for m in measures for v in shares[m]] + [1])
    bc.valueAxis.valueMin, bc.valueAxis.valueMax = 0, top * 1.25
    bc.valueAxis.labels.fontName, bc.valueAxis.labels.fontSize = FONT, 6.5
    bc.valueAxis.labelTextFormat = "%d%%"
    bc.valueAxis.strokeColor = colors.white
    bc.valueAxis.visibleGrid, bc.valueAxis.gridStrokeColor = True, LINE
    bc.categoryAxis.categoryNames = [_plain(a) for a in agents]
    bc.categoryAxis.labels.fontName, bc.categoryAxis.labels.fontSize = FONT, 7
    bc.categoryAxis.strokeColor = LINE
    bc.groupSpacing, bc.barSpacing = 10, 1.5
    for i, m in enumerate(measures):
        bc.bars[i].fillColor = colors.HexColor(colours[m])
        bc.bars[i].strokeColor = None
    d.add(bc)

    # labels above bars: same geometry reportlab uses to place grouped bars
    n_groups, n_bars = len(agents), len(measures)
    group_w = bc.width / max(n_groups, 1)
    bar_w = (group_w - bc.groupSpacing - bc.barSpacing * (n_bars - 1)) / n_bars
    for g in range(n_groups):
        for b, m in enumerate(measures):
            x = bc.x + g * group_w + bc.groupSpacing / 2 + b * (bar_w + bc.barSpacing) + bar_w / 2
            y = bc.y + bc.height * shares[m][g] / bc.valueAxis.valueMax
            d.add(String(x, y + 8, f"{shares[m][g]:.0f}%", fontName=BOLD, fontSize=6, fillColor=INK,
                         textAnchor="middle"))
            d.add(String(x, y + 2, _plain(labels[m][g]), fontName=FONT, fontSize=5, fillColor=MUTED,
                         textAnchor="middle"))

    # legend
    x = bc.x
    for m in measures:
        d.add(Rect(x, height - 10, 6, 6, fillColor=colors.HexColor(colours[m]), strokeColor=None))
        d.add(String(x + 9, height - 9.5, m, fontName=FONT, fontSize=7, fillColor=INK))
        x += 75
    return d


def build_pdf(report, title, subtitle_lines, colours):
    """report: blocks collected by show_dashboard. Returns PDF bytes."""
    buf = io.BytesIO()
    page = landscape(A4)
    margin = 12 * mm
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin,
                            topMargin=24 * mm, bottomMargin=12 * mm, title=title, author="ACL")
    width = page[0] - 2 * margin
    stamp = datetime.now().strftime("%d %b %Y, %H:%M")

    def frame(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, page[1] - 16 * mm, page[0], 16 * mm, stroke=0, fill=1)
        canvas.setFillColor(RED)
        canvas.roundRect(margin, page[1] - 12.5 * mm, 9 * mm, 9 * mm, 2 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(BOLD, 7.5)
        canvas.drawCentredString(margin + 4.5 * mm, page[1] - 9 * mm, "ACL")
        canvas.setFont(BOLD, 13)
        canvas.drawString(margin + 12 * mm, page[1] - 9 * mm, title)
        canvas.setFont(FONT, 7.5)
        canvas.drawString(margin + 12 * mm, page[1] - 13 * mm, "   ·   ".join(subtitle_lines))
        canvas.drawRightString(page[0] - margin, page[1] - 9 * mm, f"Generated {stamp}")
        canvas.setFillColor(MUTED)
        canvas.setFont(FONT, 7)
        canvas.drawRightString(page[0] - margin, 6 * mm, f"Page {_doc.page}")
        canvas.restoreState()

    story = []
    for block in report:
        kind = block[0]
        if kind == "kpis":
            story += [_kpis(block[1], width), Spacer(1, 4)]
        elif kind == "table":
            _, t_title, headers, rows, total = block
            text_cols = 2 if "Lodge mode" in headers else 1
            first = [0.16, 0.10][:text_cols]
            rest = (1 - sum(first)) / (len(headers) - text_cols)
            table = _table(headers, rows, total, col_widths=[width * f for f in first + [rest] * (len(headers) - text_cols)],
                           text_cols=text_cols)
            # short tables stay in one piece; long ones run on to the next page with the header repeated
            story += [KeepTogether([_section(t_title), table])] if len(rows) <= 18 else [_section(t_title), table]
        elif kind == "note":
            story += [Spacer(1, 2), Paragraph(_plain(block[1]), NOTE)]
        elif kind == "chart":
            _, c_title, agents, shares, labels = block
            story.append(KeepTogether([_section(c_title), _chart(agents, shares, labels, colours, width)]))
        elif kind == "lanes":
            half = (width - 8 * mm) / 2
            cells = []
            for l_title, headers, rows, tone in block[1]:
                widths = [half * f for f in (0.24, 0.13, 0.21, 0.24, 0.18)]
                cells.append([_section(l_title), _table(headers, rows, tone=tone, col_widths=widths)])
            grid = Table([[cells[0], cells[1]], [cells[2], cells[3]]], colWidths=[half + 4 * mm] * 2,
                         hAlign="LEFT")
            grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 8 * mm / 2)]))
            story.append(grid)
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buf.getvalue()
