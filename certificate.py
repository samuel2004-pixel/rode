"""
certificate.py
Generates a filled "Certificate of Completion" PDF by overlaying the
student's name and course dates on top of the centre's official
3-month / 6-month / 1-year certificate templates, using the exact
text coordinates measured from the template PDFs (pdfplumber
word/line extraction) so the result looks identical to a hand-filled
certificate.

There is no separate pre-printed "1 year" template file - the 1 year
certificate reuses the 6-month template's artwork/border and simply
overlays a small cream-coloured patch over the printed
"(Six months)" caption, replacing it with "(One year)" in the same
spot. Everything else (name position, date boxes, etc.) is identical.
"""
import io
import os
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from pypdf import PdfReader, PdfWriter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# Which physical template PDF backs each certificate "bucket".
# 12 (1 year) intentionally reuses the 6-month artwork - see module
# docstring - its duration caption is swapped by _draw_duration_label().
TEMPLATES = {
    3: os.path.join(ASSETS_DIR, "cert_3_months.pdf"),
    6: os.path.join(ASSETS_DIR, "cert_6_months.pdf"),
    12: os.path.join(ASSETS_DIR, "cert_6_months.pdf"),
}

PAGE_W, PAGE_H = 792, 612  # landscape letter, matches the templates

# Cream background colour used inside the certificate border (matches the
# template's inner panel), used to blank out printed text before writing
# the real value on top.
CREAM = Color(0.882, 0.882, 0.761)

# Coordinates below were measured directly from the certificate template
# PDFs (pdfplumber word/line extraction), in points, bottom-left origin.
NAME_CENTER_X = 501.5
NAME_BASELINE_Y = 325
NAME_FONT_SIZE = 20

DATE1_BOX = (508, 209.5, 607.5, 226)   # start date blank (x0, y0, x1, y1)
DATE2_BOX = (628.5, 209.5, 724, 226)   # end date blank
DATE_FONT_SIZE = 13

# Box covering the printed "(Six months)" caption on the 6-month
# template, so it can be blanked out and replaced with "(One year)"
# for the 1-year certificate. Measured the same way as the boxes above.
DURATION_LABEL_BOX = (430, 174, 580, 192)
DURATION_LABEL_FONT_SIZE = 14

# Text to print for buckets whose template caption needs to be
# overridden. Buckets not listed here keep the template's own
# pre-printed caption untouched.
DURATION_LABEL_OVERRIDES = {
    12: "(One year)",
}


def _bucket(duration_months):
    """Map any requested duration (in months) onto the closest
    certificate we have artwork for: 3, 6, or 12 (1 year)."""
    try:
        months = int(duration_months)
    except (TypeError, ValueError):
        months = 3
    if months >= 9:
        return 12
    if months >= 5:
        return 6
    return 3


def _draw_date(c, box, text):
    x0, y0, x1, y1 = box
    c.setFillColor(CREAM)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=0, fill=1)
    c.setFillColor(Color(0, 0, 0))
    c.setFont("Helvetica", DATE_FONT_SIZE)
    cx = (x0 + x1) / 2
    cy = y0 + (y1 - y0) / 2 - 4
    c.drawCentredString(cx, cy, text)


def _draw_duration_label(c, bucket):
    text = DURATION_LABEL_OVERRIDES.get(bucket)
    if not text:
        return
    x0, y0, x1, y1 = DURATION_LABEL_BOX
    c.setFillColor(CREAM)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=0, fill=1)
    c.setFillColor(Color(0, 0, 0))
    c.setFont("Helvetica-Oblique", DURATION_LABEL_FONT_SIZE)
    cx = (x0 + x1) / 2
    cy = y0 + (y1 - y0) / 2 - 4
    c.drawCentredString(cx, cy, text)


def generate_certificate(name, duration_months, start_date, end_date):
    """
    name: student's full name (str)
    duration_months: 3, 6, or 12/1-year worth of months (int) - any
        value is rounded to the nearest certificate we have artwork
        for (see _bucket()).
    start_date, end_date: strings already formatted as DD/MM/YYYY
    Returns: bytes of the finished, filled certificate PDF.
    """
    bucket = _bucket(duration_months)
    template_path = TEMPLATES[bucket]

    if not os.path.exists(template_path):
        raise FileNotFoundError(
            f"Certificate template missing on disk: {template_path}. "
            "Make sure the 'assets' folder was deployed alongside the app."
        )

    safe_name = (name or "").strip() or "Student"
    safe_start = start_date or ""
    safe_end = end_date or ""

    # Build the overlay (name + dates + any caption override) as its
    # own single-page PDF
    overlay_buf = io.BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(PAGE_W, PAGE_H))

    c.setFillColor(Color(0, 0, 0))
    c.setFont("Helvetica-Bold", NAME_FONT_SIZE)
    c.drawCentredString(NAME_CENTER_X, NAME_BASELINE_Y, safe_name)

    _draw_date(c, DATE1_BOX, safe_start)
    _draw_date(c, DATE2_BOX, safe_end)
    _draw_duration_label(c, bucket)

    c.save()
    overlay_buf.seek(0)

    # Merge overlay onto the template
    base_reader = PdfReader(template_path)
    overlay_reader = PdfReader(overlay_buf)

    writer = PdfWriter()
    base_page = base_reader.pages[0]
    base_page.merge_page(overlay_reader.pages[0])
    writer.add_page(base_page)

    out_buf = io.BytesIO()
    writer.write(out_buf)
    return out_buf.getvalue()
