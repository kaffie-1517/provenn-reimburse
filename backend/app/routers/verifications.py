import asyncio
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import Select, func, select

from app import metrics, pdf
from app.deps import Session, require, tenant_id
from app.export import approved_workbook
from app.models import Approval, Invoice, Result, Role, User, Verification
from app.routers.invoices import read_pdf_upload
from app.schemas import DecisionIn, InvoiceSummary, Page, VerificationOut
from app.security import Claims

router = APIRouter(prefix="/api/v1/verifications", tags=["verifications"])

EmployeeClaims = Annotated[Claims, Depends(require(Role.EMPLOYEE))]
ReviewerClaims = Annotated[Claims, Depends(require(Role.EMPLOYEE, Role.COMPANY_ADMIN))]
AdminClaims = Annotated[Claims, Depends(require(Role.COMPANY_ADMIN))]


def to_out(v: Verification) -> VerificationOut:
    inv = v.invoice
    return VerificationOut(
        id=v.id,
        result=v.result,
        approval_status=v.approval_status,
        extracted_code=v.extracted_code,
        submitted_hash=v.submitted_hash,
        file_name=v.file_name,
        submitted_at=v.submitted_at,
        submitter_email=v.submitter.email,
        submitter_name=v.submitter.name,
        approved_at=v.approved_at,
        invoice=InvoiceSummary(
            reference_code=inv.reference_code,
            vendor_name=inv.vendor_name,
            amount_cents=inv.amount_cents,
            currency=inv.currency,
            invoice_date=inv.invoice_date,
        )
        if inv
        else None,
    )


def _file_name(upload: UploadFile) -> str | None:
    name = os.path.basename(upload.filename or "").strip()
    return name[:255] or None


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit(
    claims: EmployeeClaims,
    session: Session,
    pdf_file: Annotated[UploadFile, File(alias="pdf")],
) -> VerificationOut:
    data = await read_pdf_upload(pdf_file)
    digest = pdf.sha256(data)
    code = await asyncio.to_thread(pdf.find_code, data)

    invoice = None
    if code:
        invoice = await session.scalar(select(Invoice).where(Invoice.reference_code == code))

    matched = None
    if invoice is None:
        result = Result.NOT_FOUND
    else:
        await session.refresh(invoice, ["versions"])
        matched = next((ver for ver in invoice.versions if ver.sha256_hash == digest), None)
        result = Result.MATCH if matched else Result.MISMATCH

    v = Verification(
        company_id=tenant_id(claims),  # from the token, never the request
        submitted_by=claims.user_id,
        invoice_id=invoice.id if invoice else None,
        extracted_code=code,
        submitted_hash=digest,
        matched_version_id=matched.id if matched else None,
        file_name=_file_name(pdf_file),
        result=result,
    )
    session.add(v)
    await session.commit()
    metrics.VERIFICATIONS.labels(result).inc()

    v = await session.get(Verification, v.id, populate_existing=True)
    return to_out(v)


def _scoped(claims: Claims) -> Select:
    q = select(Verification)
    if claims.role == Role.COMPANY_ADMIN:
        return q.where(Verification.company_id == tenant_id(claims))
    return q.where(Verification.submitted_by == claims.user_id)


@router.get("")
async def list_verifications(
    claims: ReviewerClaims,
    session: Session,
    result: Literal["match", "mismatch", "not_found"] | None = None,
    approval_status: Literal["pending", "approved", "rejected"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[VerificationOut]:
    q = _scoped(claims)
    if result:
        q = q.where(Verification.result == result)
    if approval_status:
        q = q.where(Verification.approval_status == approval_status)

    total = await session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = await session.scalars(
        q.order_by(Verification.submitted_at.desc(), Verification.id).limit(limit).offset(offset)
    )
    return Page[VerificationOut](items=[to_out(v) for v in rows.unique()], total=total)


@router.get("/export")
async def export_approved(claims: AdminClaims, session: Session) -> Response:
    rows = list(
        (
            await session.scalars(
                select(Verification)
                .where(
                    Verification.company_id == tenant_id(claims),
                    Verification.approval_status == Approval.APPROVED,
                )
                .order_by(Verification.approved_at)
            )
        ).unique()
    )
    approver_ids = {v.approved_by for v in rows if v.approved_by}
    approvers = (
        dict(
            (
                await session.execute(select(User.id, User.name).where(User.id.in_(approver_ids)))
            ).all()
        )
        if approver_ids
        else {}
    )
    body = await asyncio.to_thread(approved_workbook, rows, approvers)
    name = f"approved-reimbursements-{datetime.now(UTC):%Y-%m-%d}.xlsx"
    return Response(
        body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.patch("/{verification_id}")
async def decide(
    verification_id: uuid.UUID,
    body: DecisionIn,
    claims: AdminClaims,
    session: Session,
) -> VerificationOut:
    # Scoped by company in the query itself: another tenant's id is a 404,
    # indistinguishable from an id that doesn't exist.
    v = await session.scalar(
        select(Verification)
        .where(
            Verification.id == verification_id,
            Verification.company_id == tenant_id(claims),
        )
        .with_for_update(of=Verification)
    )
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verification not found")
    if v.approval_status != Approval.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {v.approval_status}")

    # The decision is recorded alongside, never instead of, the machine result.
    v.approval_status = body.decision
    v.approved_by = claims.user_id
    v.approved_at = datetime.now(UTC)
    await session.commit()
    return to_out(v)
