import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app import jobs, metrics, pdf, refcode
from app.config import get_settings
from app.deps import Session, current_partner, require
from app.models import BillingEvent, Invoice, InvoiceStatus, Partner, Role
from app.schemas import InvoiceIssued, InvoicePublic, InvoiceRow
from app.security import Claims
from app.storage import NotFound, Storage, get_storage, raw_key
from app.worker import STAMP_INVOICE

router = APIRouter(prefix="/api/v1", tags=["invoices"])

StorageDep = Annotated[Storage, Depends(get_storage)]
_CODE_ATTEMPTS = 5


async def read_pdf_upload(upload: UploadFile) -> bytes:
    """Reads an upload, enforcing the size limit and that it's actually a PDF."""
    limit = get_settings().max_upload_bytes
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File is larger than {get_settings().max_upload_mb} MB",
        )
    if not pdf.looks_like_pdf(data):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a PDF file")
    return data


class InvoiceForm:
    """Multipart fields shared by the provider and partner endpoints."""

    def __init__(
        self,
        pdf_file: Annotated[UploadFile, File(alias="pdf")],
        vendor_name: Annotated[str, Form(min_length=1, max_length=200)],
        amount_cents: Annotated[int, Form(gt=0, le=10**11)],
        invoice_date: Annotated[date, Form()],
        currency: Annotated[str, Form(pattern=r"^[A-Za-z]{3}$")] = "INR",
        purchase_ref: Annotated[str | None, Form(max_length=100)] = None,
    ):
        self.pdf_file = pdf_file
        self.vendor_name = vendor_name.strip()
        self.amount_cents = amount_cents
        self.invoice_date = invoice_date
        self.currency = currency.upper()
        self.purchase_ref = (purchase_ref or "").strip() or None


async def _issue(
    session: Session,
    storage: Storage,
    form: InvoiceForm,
    *,
    provider_id: uuid.UUID | None = None,
    partner_id: uuid.UUID | None = None,
    source: str,
) -> InvoiceIssued:
    raw = await read_pdf_upload(form.pdf_file)
    invoice_id = uuid.uuid4()
    # Upload first: if the DB insert then fails we only leave an orphan file,
    # never a job that points at a missing one.
    await storage.put(raw_key(invoice_id), raw)

    for attempt in range(_CODE_ATTEMPTS):
        invoice = Invoice(
            id=invoice_id,
            reference_code=refcode.new_code(),
            provider_user_id=provider_id,
            partner_id=partner_id,
            vendor_name=form.vendor_name,
            amount_cents=form.amount_cents,
            currency=form.currency,
            invoice_date=form.invoice_date,
            purchase_ref=form.purchase_ref,
            status=InvoiceStatus.PROCESSING,
        )
        session.add(invoice)
        jobs.enqueue(session, STAMP_INVOICE, {"invoice_id": str(invoice_id)})
        try:
            await session.commit()
            break
        except IntegrityError as e:
            await session.rollback()
            if "reference_code" not in str(e.orig) or attempt == _CODE_ATTEMPTS - 1:
                raise
    metrics.INVOICES_ISSUED.labels(source).inc()
    return InvoiceIssued(
        invoice_id=invoice.id, reference_code=invoice.reference_code, status=invoice.status
    )


@router.post("/invoices", status_code=status.HTTP_202_ACCEPTED)
async def issue_as_provider(
    form: Annotated[InvoiceForm, Depends()],
    claims: Annotated[Claims, Depends(require(Role.PROVIDER))],
    session: Session,
    storage: StorageDep,
) -> InvoiceIssued:
    return await _issue(session, storage, form, provider_id=claims.user_id, source="provider")


@router.post("/partner/invoices", status_code=status.HTTP_202_ACCEPTED, tags=["partner"])
async def issue_as_partner(
    form: Annotated[InvoiceForm, Depends()],
    partner: Annotated[Partner, Depends(current_partner)],
    session: Session,
    storage: StorageDep,
) -> InvoiceIssued:
    return await _issue(session, storage, form, partner_id=partner.id, source="partner")


def _public(inv: Invoice) -> dict:
    return {
        "reference_code": inv.reference_code,
        "status": inv.status,
        "ready": inv.status == InvoiceStatus.READY,
        "vendor_name": inv.vendor_name,
        "amount_cents": inv.amount_cents,
        "currency": inv.currency,
        "invoice_date": inv.invoice_date,
        "issued_at": inv.created_at,
    }


@router.get("/invoices/mine")
async def my_invoices(
    claims: Annotated[Claims, Depends(require(Role.PROVIDER))],
    session: Session,
    limit: int = 100,
) -> list[InvoiceRow]:
    downloaded = exists().where(BillingEvent.invoice_id == Invoice.id)
    rows = await session.execute(
        select(Invoice, downloaded.label("downloaded"))
        .where(Invoice.provider_user_id == claims.user_id)
        .order_by(Invoice.created_at.desc())
        .limit(min(max(limit, 1), 500))
    )
    return [
        InvoiceRow(
            **_public(inv), id=inv.id, purchase_ref=inv.purchase_ref, downloaded=was_downloaded
        )
        for inv, was_downloaded in rows
    ]


async def _by_code(session: Session, raw_code: str) -> Invoice:
    code = refcode.normalize(raw_code)
    inv = (
        await session.scalar(select(Invoice).where(Invoice.reference_code == code))
        if code
        else None
    )
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No invoice with that reference code")
    return inv


@router.get("/invoices/{code}")
async def invoice_status(code: str, session: Session) -> InvoicePublic:
    return InvoicePublic(**_public(await _by_code(session, code)))


@router.get(
    "/invoices/{code}/download",
    responses={200: {"content": {"application/pdf": {}}}, 202: {"description": "Not ready"}},
)
async def download(code: str, session: Session, storage: StorageDep):
    inv = await _by_code(session, code)
    if inv.status != InvoiceStatus.READY:
        return JSONResponse(
            {"detail": "Invoice is still being prepared", "status": inv.status},
            status_code=status.HTTP_202_ACCEPTED,
        )
    await session.refresh(inv, ["versions"])
    latest = inv.versions[-1]
    try:
        data = await storage.get(latest.storage_key)
    except NotFound as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "File temporarily unavailable"
        ) from e

    # Billing: one event per invoice, on first successful download. The unique
    # idempotency key makes concurrent first downloads safe.
    result = await session.execute(
        insert(BillingEvent)
        .values(
            id=uuid.uuid4(),
            invoice_id=inv.id,
            idempotency_key=f"download:{inv.id}",
            amount_cents=inv.amount_cents,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    await session.commit()
    if result.rowcount:
        metrics.DOWNLOADS_BILLED.inc()

    name = f"invoice-{refcode.display(inv.reference_code)}.pdf"
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )
