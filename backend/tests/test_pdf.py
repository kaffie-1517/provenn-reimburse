import io

import pytest
from pypdf import PdfReader

from app import pdf, refcode
from tests.pdfs import invoice_pdf, tamper


def test_refcode_shape_and_normalize():
    codes = {refcode.new_code() for _ in range(200)}
    assert len(codes) == 200
    assert all(refcode.CODE_RE.match(c) for c in codes)
    assert refcode.normalize(" pnn-abcd2345 ") == "ABCD2345"
    assert refcode.normalize("ABCD2345") == "ABCD2345"
    assert refcode.normalize("ABCD1345") is None  # 1 isn't base32
    assert refcode.normalize("short") is None


def test_stamp_keeps_pages_and_is_readable():
    raw = invoice_pdf(pages=3)
    out = pdf.stamp(raw, "ABCD2345")
    reader = PdfReader(io.BytesIO(out))
    assert len(reader.pages) == 3
    for page in reader.pages:
        assert "PNN-ABCD2345" in page.extract_text()


@pytest.mark.parametrize("finder", ["marker", "text", "qr"])
def test_code_round_trip(finder):
    stamped = pdf.stamp(invoice_pdf(), "QRST2345", qr_payload="https://app.example.com/i/QRST2345")
    reader = PdfReader(io.BytesIO(stamped))
    if finder == "marker":
        assert pdf.find_code(pdf.with_marker(stamped, "QRST2345")) == "QRST2345"
    elif finder == "text":
        assert pdf._from_text(reader) == "QRST2345"
    else:
        assert pdf._from_qr(reader) == "QRST2345"


def test_marker_is_idempotent_and_file_still_opens():
    raw = invoice_pdf()
    once = pdf.with_marker(raw, "ABCD2345")
    assert pdf.with_marker(once, "ABCD2345") == once
    assert once.startswith(raw)
    assert len(PdfReader(io.BytesIO(once)).pages) == 1


def test_any_edit_changes_the_hash():
    issued = pdf.with_marker(pdf.stamp(invoice_pdf(), "ABCD2345"), "ABCD2345")
    forged = tamper(issued)
    assert pdf.sha256(forged) != pdf.sha256(issued)
    # ...but the code still reads back, so the result is "mismatch", not "not_found".
    assert pdf.find_code(forged) == "ABCD2345"


def test_unreadable_input_is_not_found_not_crash():
    assert pdf.find_code(b"not a pdf at all") is None
    assert pdf.find_code(b"%PDF-1.7 garbage") is None
    with pytest.raises(pdf.StampError):
        pdf.stamp(b"%PDF-1.7 garbage", "ABCD2345")


def test_looks_like_pdf():
    assert pdf.looks_like_pdf(invoice_pdf())
    assert not pdf.looks_like_pdf(b"\x89PNG....")
