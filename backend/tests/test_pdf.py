import io

import pytest
from pypdf import PdfReader, PdfWriter

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
        assert pdf._from_text(reader) == ["QRST2345"]
    else:
        assert pdf._from_qr(reader) == ["QRST2345"]


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


async def test_local_storage_round_trip(tmp_path):
    from app.storage import LocalStorage, NotFound

    store = LocalStorage(str(tmp_path))
    await store.put("invoices/x/v1.pdf", b"%PDF-1.7 data")
    assert await store.get("invoices/x/v1.pdf") == b"%PDF-1.7 data"
    with pytest.raises(NotFound):
        await store.get("invoices/missing.pdf")
    with pytest.raises(ValueError):
        await store.put("../../escape.pdf", b"x")


def test_connect_options_for_hosted_postgres():
    from app.db import connect_options

    url, args = connect_options("postgresql+asyncpg://u:p@db.example.com:5432/app?sslmode=require")
    assert url == "postgresql+asyncpg://u:p@db.example.com:5432/app" and args == {"ssl": "require"}

    url, args = connect_options("postgresql+asyncpg://u:p@pooler.example.com:6543/postgres")
    assert args == {"statement_cache_size": 0}
    assert url.endswith("?prepared_statement_cache_size=0")

    url, args = connect_options("postgresql+asyncpg://u@localhost/app")
    assert (url, args) == ("postgresql+asyncpg://u@localhost/app", {})


def resave(data: bytes, edit: tuple[bytes, bytes] | None = None) -> bytes:
    """What an online PDF editor does: parse and rewrite the whole file,
    which drops anything after the original trailer (our marker included)."""
    if edit:
        data = data.replace(*edit)
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_code_survives_an_editor_rewrite():
    issued = pdf.with_marker(pdf.stamp(invoice_pdf(), "ABCD2345"), "ABCD2345")
    edited = resave(issued, (b"1,500.00", b"9,500.00"))
    assert b"% REF:" not in edited  # marker gone, like a real editor
    assert pdf.find_code(edited) == "ABCD2345"
    assert pdf.sha256(edited) != pdf.sha256(issued)


def test_double_stamp_lists_newest_code_first():
    once = pdf.with_marker(pdf.stamp(invoice_pdf(), "OLDC2345"), "OLDC2345")
    twice = pdf.with_marker(pdf.stamp(once, "NEWC2345"), "NEWC2345")
    assert pdf.candidate_codes(twice)[0] == "NEWC2345"
    # Even after an editor strips the marker, the newest stamp wins.
    assert pdf.candidate_codes(resave(twice))[:2] == ["NEWC2345", "OLDC2345"]
