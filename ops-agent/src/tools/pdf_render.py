"""Render Asantico estimates and invoices in the real business letterhead format.

This is the document format Asantico actually sends to Avenue One Residential:
green letterhead, BILL TO / JOB SITE blocks, a scope-of-work section, the priced
line-item table, notes & terms, and a signature block. It uses ReportLab (already
a dependency via asantico-cli) and needs no network, so documents generate fully
offline in the field.

Business invariants honored here: company is "Asantico" (never "Asantico LLC"),
sales tax is Seattle 10.55% on every line including labor, and no tenant names
appear on documents - work is billed to the property manager.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

TAX_RATE = Decimal("0.1055")

# -- Brand ------------------------------------------------------------------ #
GREEN_DARK = colors.HexColor("#1F4A33")
GREEN_BAND = colors.HexColor("#EFF3EE")
GREY_TEXT = colors.HexColor("#6B6B6B")
RULE = colors.HexColor("#2A2A2A")

COMPANY_NAME = "ASANTICO"
COMPANY_TAG = "PROPERTY MAINTENANCE & REPAIR"
COMPANY_CONTACT = ["1702 11th Ave S, B208", "Seattle, WA 98134",
                   "(360) 388-3006", "eyobkidane2@gmail.com"]
SUBMITTED_BY = ["Eyob (Stark) Worku", "Asantico — Owner"]

# Default client block: Avenue One Residential is the primary client
# (see knowledge/client-accounts.md).
DEFAULT_BILL_TO = ["<b>Avenue One Residential</b>", "Attn: Saniya Zaveri",
                   "2212 Queen Anne Ave. N. #724", "Seattle, WA 98109",
                   "(206) 558-2768"]

ESTIMATE_TERMS = [
    "Estimate valid for 30 days from the date above.",
    "Final invoice may vary if additional issues are discovered during work.",
    "Sales tax calculated at the Seattle combined rate of 10.55%.",
    "Owner approval required before commencing work per Avenue One vendor policy.",
    "Payment due net 30 upon receipt of final invoice.",
]
INVOICE_TERMS = [
    "Payment due net 30 from the date above.",
    "Sales tax calculated at the Seattle combined rate of 10.55%.",
    "Make checks payable to Asantico, Seattle WA.",
    "Questions: contact Asantico directly.",
]

# -- Styles ------------------------------------------------------------------ #
S_COMPANY = ParagraphStyle("company", fontName="Helvetica-Bold", fontSize=22,
                           textColor=GREEN_DARK, leading=24)
S_TAG = ParagraphStyle("tag", fontName="Helvetica", fontSize=8,
                       textColor=GREY_TEXT, leading=11)
S_CONTACT = ParagraphStyle("contact", fontName="Helvetica", fontSize=9,
                           leading=12, alignment=TA_RIGHT)
S_DOCTITLE = ParagraphStyle("doctitle", fontName="Helvetica-Bold", fontSize=24,
                            textColor=GREEN_DARK, leading=26)
S_DOCMETA = ParagraphStyle("docmeta", fontName="Helvetica", fontSize=9.5,
                           textColor=GREY_TEXT, leading=13)
S_BLOCKHEAD = ParagraphStyle("blockhead", fontName="Helvetica-Bold", fontSize=9,
                             textColor=GREEN_DARK)
S_BLOCK = ParagraphStyle("block", fontName="Helvetica", fontSize=10, leading=14)
S_SECTION = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11,
                           textColor=GREEN_DARK, spaceBefore=6, spaceAfter=4)
S_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14)
S_BULLET = ParagraphStyle("bullet", parent=S_BODY, leftIndent=16,
                          bulletIndent=6, spaceAfter=1)
S_TERMS = ParagraphStyle("terms", parent=S_BODY, fontSize=8.5, leading=12,
                         leftIndent=12, bulletIndent=4)
S_SIGN = ParagraphStyle("sign", fontName="Helvetica", fontSize=9.5, leading=13)


def _money(x: Decimal) -> str:
    return f"${x.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"


def render_document(doc_type: str, doc_number: str, doc_date: date,
                    property: str, unit: str, line_items: list[dict],
                    out_dir: str | Path, work_order: str | None = None,
                    job_site_lines: list[str] | None = None,
                    scope_intro: str | None = None,
                    scope_items: list[str] | None = None) -> str:
    """Write an estimate or invoice PDF in the Asantico letterhead format.

    line_items: [{"description": str, "amount": float, "qty": int?}, ...]
    Returns the path of the written file.
    """
    is_estimate = doc_type == "estimate"
    title = "ESTIMATE" if is_estimate else "INVOICE"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in property.lower()).strip("-")
    path = out_dir / f"{doc_type}_{slug}_{unit or 'na'}_{doc_number}.pdf"

    frame_width = letter[0] - 1.2 * inch
    story = []

    # Letterhead: company left, contact block right, heavy rule under.
    head = Table(
        [[
            [Paragraph(COMPANY_NAME, S_COMPANY), Paragraph(COMPANY_TAG, S_TAG)],
            Paragraph("<br/>".join(COMPANY_CONTACT), S_CONTACT),
        ]],
        colWidths=[frame_width * 0.55, frame_width * 0.45],
    )
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(head)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.4, color=RULE))
    story.append(Spacer(1, 16))

    story.append(Paragraph(title, S_DOCTITLE))
    meta = (f"{title.title()} #: {doc_number} &nbsp;|&nbsp; "
            f"Date: {doc_date.strftime('%B %d, %Y')}")
    if work_order:
        meta += f" &nbsp;|&nbsp; Work Order: {work_order}"
    story.append(Paragraph(meta, S_DOCMETA))
    story.append(Spacer(1, 12))

    # BILL TO / JOB SITE
    job_site = job_site_lines or [f"<b>{property} #{unit}</b>" if unit
                                  else f"<b>{property}</b>", "Seattle, WA"]
    parties = Table(
        [
            [Paragraph("BILL TO", S_BLOCKHEAD), Paragraph("JOB SITE", S_BLOCKHEAD)],
            [Paragraph("<br/>".join(DEFAULT_BILL_TO), S_BLOCK),
             Paragraph("<br/>".join(job_site), S_BLOCK)],
        ],
        colWidths=[frame_width / 2, frame_width / 2],
    )
    parties.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_BAND),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 1), (-1, 1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(parties)
    story.append(Spacer(1, 16))

    # SCOPE OF WORK
    scope_items = scope_items or [li.get("description", "line") for li in line_items]
    if scope_items:
        story.append(Paragraph("SCOPE OF WORK", S_SECTION))
        intro = scope_intro or (
            f"Maintenance and repairs at {property}"
            f"{' #' + unit if unit else ''} for Avenue One Residential. "
            "The following items are included in this "
            f"{'estimate' if is_estimate else 'invoice'}:")
        story.append(Paragraph(intro, S_BODY))
        story.append(Spacer(1, 4))
        for item in scope_items:
            story.append(Paragraph(item, S_BULLET, bulletText="•"))
        story.append(Spacer(1, 14))

    # Line-item table with per-line 10.55% tax on everything, labor included.
    rows = [["DESCRIPTION", "QTY", "RATE", "AMOUNT"]]
    subtotal = Decimal("0")
    for li in line_items:
        qty = int(li.get("qty", 1))
        rate = Decimal(str(li.get("amount", 0)))
        amount = rate * qty
        subtotal += amount
        rows.append([Paragraph(li.get("description", "line"), S_BODY),
                     str(qty), _money(rate), _money(amount)])
    tax = (subtotal * TAX_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal + tax

    items = Table(rows, colWidths=[frame_width - 2.7 * inch, 0.6 * inch,
                                   1.05 * inch, 1.05 * inch], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), GREEN_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (0, -1), 10),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, colors.HexColor("#E3E3E3")),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), GREEN_BAND))
    items.setStyle(TableStyle(style))
    story.append(items)
    story.append(Spacer(1, 10))

    totals = Table(
        [["Subtotal", _money(subtotal)],
         ["Sales Tax (Seattle, 10.55%)", _money(tax)],
         ["TOTAL", _money(total)]],
        colWidths=[frame_width - 1.35 * inch, 1.35 * inch],
    )
    totals.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 2), (-1, 2), GREEN_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, 2), (-1, 2), 0.9, RULE),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 10),
    ]))
    story.append(totals)
    story.append(Spacer(1, 18))

    story.append(Paragraph("NOTES &amp; TERMS", S_SECTION))
    for term in (ESTIMATE_TERMS if is_estimate else INVOICE_TERMS):
        story.append(Paragraph(term, S_TERMS, bulletText="•"))
    story.append(Spacer(1, 26))

    sign = Table(
        [[Paragraph("Submitted by:<br/><b>" + SUBMITTED_BY[0] + "</b><br/>"
                    + SUBMITTED_BY[1], S_SIGN),
          Paragraph("Approved by (Avenue One):<br/><br/>"
                    "_______________________________<br/>Signature &amp; Date",
                    S_SIGN)]],
        colWidths=[frame_width / 2, frame_width / 2],
    )
    sign.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
    ]))
    story.append(sign)

    doc = SimpleDocTemplate(str(path), pagesize=letter,
                            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.55 * inch, bottomMargin=0.55 * inch,
                            title=f"Asantico {title.title()} {doc_number}")
    doc.build(story)
    return str(path)
