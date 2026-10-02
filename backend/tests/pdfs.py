"""Builds small but real PDFs for tests."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def invoice_pdf(vendor: str = "Acme Supplies", amount: str = "1,500.00", pages: int = 1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for n in range(pages):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(72, 760, f"INVOICE — {vendor}")
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, f"Amount due: INR {amount}")
        c.drawString(72, 700, f"Page {n + 1} of {pages}")
        c.showPage()
    c.save()
    return buf.getvalue()


def tamper(pdf: bytes, old: bytes = b"1,500.00", new: bytes = b"9,500.00") -> bytes:
    """Edits bytes in place, the way a forged amount would."""
    assert old in pdf, "fixture text not found"
    return pdf.replace(old, new, 1)
