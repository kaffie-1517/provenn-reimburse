"""PDF handling: stamping issued invoices and reading codes back from submissions.

Issuing:   stamp(raw, code) -> QR + "PNN-XXXXXXXX" footer on every page,
           then with_marker() appends a plain-text marker, then sha256().
Verifying: find_code(submitted) tries the marker, the page text, then any
           QR code in the page images (covers printed-and-scanned copies).
"""

import hashlib
import io
import logging
import re

import qrcode
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.refcode import display

log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
_MARKER_RE = re.compile(rb"% REF: ([A-Z2-7]{8})")
_TEXT_RE = re.compile(r"PNN-([A-Z2-7]{8})")
# QR payload is either "PNN-XXXXXXXX" or a status URL ending in /i/XXXXXXXX.
_QR_RE = re.compile(r"(?:PNN-|/i/)([A-Z2-7]{8})\b")


class StampError(Exception):
    """The PDF can't be stamped (encrypted, malformed, ...)."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def looks_like_pdf(data: bytes) -> bool:
    return data[:1024].lstrip().startswith(PDF_MAGIC)


# ── issuing ─────────────────────────────────────────────────────────────────


def _qr_png(payload: str) -> Image.Image:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").get_image()


def _footer(width: float, height: float, code: str, qr: Image.Image) -> bytes:
    """A one-page PDF the size of the target page with just the stamp on it."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    size = max(42.0, min(width, height) * 0.09)
    margin = size * 0.35
    c.drawImage(ImageReader(qr), width - margin - size, margin, size, size)

    c.setFillColor(Color(0.25, 0.22, 0.18))
    c.setFont("Helvetica-Bold", 8)
    c.drawRightString(width - margin * 2 - size, margin + size * 0.55, display(code))
    c.setFont("Helvetica", 6.5)
    c.setFillColor(Color(0.45, 0.41, 0.36))
    c.drawRightString(
        width - margin * 2 - size, margin + size * 0.3, "Verify this invoice with ProveNN"
    )
    c.showPage()
    c.save()
    return buf.getvalue()


def stamp(raw: bytes, code: str, qr_payload: str | None = None) -> bytes:
    """Returns a new PDF with the stamp drawn on every page."""
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise StampError("PDF is encrypted")
        qr = _qr_png(qr_payload or display(code))
        writer = PdfWriter(clone_from=reader)
        overlays: dict[tuple[float, float], bytes] = {}
        for page in writer.pages:
            box = page.mediabox
            dims = (float(box.width), float(box.height))
            if dims not in overlays:
                overlays[dims] = _footer(*dims, code, qr)
            overlay = PdfReader(io.BytesIO(overlays[dims])).pages[0]
            page.merge_translated_page(overlay, float(box.left), float(box.bottom))
        writer.add_metadata({"/ProveNNReference": code})
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except StampError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise StampError(str(e)) from e


_STARTXREF_RE = re.compile(rb"startxref\s+(\d+)\s+%%EOF\s*$")


def with_marker(pdf: bytes, code: str) -> bytes:
    """Appends a "% REF: <code>" comment that survives any later processing.

    Readers locate the xref table through the `startxref` line right before
    the final %%EOF, so after the comment we repeat the original pointer and
    a fresh %%EOF; the file stays valid for strict parsers. No-op if the
    marker is already present.
    """
    marker = b"% REF: " + code.encode()
    if marker in pdf:
        return pdf
    tail = _STARTXREF_RE.search(pdf[-1024:])
    pointer = b"startxref\n" + tail.group(1) + b"\n%%EOF\n" if tail else b""
    sep = b"" if pdf.endswith(b"\n") else b"\n"
    return pdf + sep + marker + b"\n" + pointer


# ── verifying ───────────────────────────────────────────────────────────────


def _from_marker(data: bytes) -> str | None:
    found = _MARKER_RE.findall(data)
    return found[-1].decode() if found else None


def _from_text(reader: PdfReader) -> str | None:
    for page in reader.pages[:5]:
        m = _TEXT_RE.search(page.extract_text() or "")
        if m:
            return m.group(1)
    return None


def _from_qr(reader: PdfReader) -> str | None:
    import zxingcpp  # imported lazily: native module, only needed here

    for page in reader.pages[:5]:
        for img in page.images:
            try:
                pil = img.image
            except Exception:  # undecodable image streams are common; skip them
                continue
            if pil is None:
                continue
            for hit in zxingcpp.read_barcodes(pil):
                m = _QR_RE.search(hit.text)
                if m:
                    return m.group(1)
    return None


def find_code(data: bytes) -> str | None:
    """Best-effort reference code extraction from a submitted file."""
    if code := _from_marker(data):
        return code
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return None
        return _from_text(reader) or _from_qr(reader)
    except Exception as e:  # a broken upload is a not_found, never a 500
        log.info("find_code: unreadable PDF: %s", e)
        return None
