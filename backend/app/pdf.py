"""PDF handling: stamping issued invoices and reading codes back from submissions.

Issuing:   stamp(raw, code) -> QR + "PNN-XXXXXXXX" footer on every page,
           then with_marker() appends a plain-text marker, then sha256().
Verifying: candidate_codes() / qr_codes() list every code found (marker,
           metadata, page text, QR images), newest stamp first; the
           verifier uses the first one that was actually issued.
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

from app import refcode
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
#
# A file can carry more than one code: an invoice that was stamped twice, or a
# stale stamp copied in from another PDF. So extraction returns *candidates*,
# newest stamp first, and the caller keeps the first one that was really issued.


def _dedupe(codes: list[str]) -> list[str]:
    return list(dict.fromkeys(codes))


def _from_marker(data: bytes) -> list[str]:
    # Markers are appended, so the last one is the newest.
    return [c.decode() for c in reversed(_MARKER_RE.findall(data))]


def _from_metadata(reader: PdfReader) -> list[str]:
    try:
        code = (reader.metadata or {}).get("/ProveNNReference")
    except Exception:
        return []
    return [str(code)] if code and refcode.CODE_RE.match(str(code)) else []


def _from_text(reader: PdfReader) -> list[str]:
    codes: list[str] = []
    for page in reader.pages[:5]:
        # A later stamp is drawn after an earlier one, so read matches backwards.
        codes += reversed(_TEXT_RE.findall(page.extract_text() or ""))
    return codes


def _from_qr(reader: PdfReader) -> list[str]:
    import zxingcpp  # imported lazily: native module, only needed here

    codes: list[str] = []
    for page in reader.pages[:5]:
        for img in page.images:
            try:
                pil = img.image
            except Exception:  # undecodable image streams are common; skip them
                continue
            if pil is None:
                continue
            for hit in zxingcpp.read_barcodes(pil):
                codes += _QR_RE.findall(hit.text)
    return list(reversed(codes))


def _reader(data: bytes) -> PdfReader | None:
    try:
        reader = PdfReader(io.BytesIO(data))
        return None if reader.is_encrypted else reader
    except Exception as e:  # a broken upload is a not_found, never a 500
        log.info("unreadable PDF: %s", e)
        return None


def candidate_codes(data: bytes) -> list[str]:
    """Cheap candidates, newest first: trailing marker, metadata, page text."""
    codes = _from_marker(data)
    reader = _reader(data)
    if reader is not None:
        try:
            codes += _from_metadata(reader) + _from_text(reader)
        except Exception as e:
            log.info("text extraction failed: %s", e)
    return _dedupe(codes)


def qr_codes(data: bytes) -> list[str]:
    """Slower fallback: decode QR codes in page images (printed-and-scanned copies)."""
    reader = _reader(data)
    if reader is None:
        return []
    try:
        return _dedupe(_from_qr(reader))
    except Exception as e:
        log.info("QR extraction failed: %s", e)
        return []


def find_code(data: bytes) -> str | None:
    """The single most likely reference code, without checking it was issued."""
    return next(iter(candidate_codes(data) or qr_codes(data)), None)
