import uuid
from datetime import date, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── auth ─────────────────────────────────────────────────────────────────────


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # platform_admin accounts are never self-service.
    role: Literal["provider", "employee", "company_admin"]
    # company_admin: creates this company. employee: joins with join_code.
    company_name: str | None = Field(None, min_length=2, max_length=200)
    join_code: str | None = Field(None, min_length=6, max_length=12)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORM):
    id: uuid.UUID
    name: str
    email: str
    role: str
    company_id: uuid.UUID | None
    company_name: str | None = None
    # Only shown to company admins, so they can invite employees.
    join_code: str | None = None


class SessionOut(BaseModel):
    token: str
    user: UserOut


# ── invoices ─────────────────────────────────────────────────────────────────


class InvoiceIssued(BaseModel):
    invoice_id: uuid.UUID
    reference_code: str
    status: str


class InvoicePublic(BaseModel):
    reference_code: str
    status: str
    ready: bool
    vendor_name: str
    amount_cents: int
    currency: str
    invoice_date: date
    issued_at: datetime


class InvoiceRow(InvoicePublic):
    id: uuid.UUID
    purchase_ref: str | None
    downloaded: bool


# ── verifications ────────────────────────────────────────────────────────────


class InvoiceSummary(BaseModel):
    reference_code: str
    vendor_name: str
    amount_cents: int
    currency: str
    invoice_date: date


class VerificationOut(BaseModel):
    id: uuid.UUID
    result: Literal["match", "mismatch", "not_found"]
    approval_status: Literal["pending", "approved", "rejected"]
    extracted_code: str | None
    submitted_hash: str
    file_name: str | None
    submitted_at: datetime
    submitter_email: str
    submitter_name: str
    approved_at: datetime | None
    invoice: InvoiceSummary | None


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
