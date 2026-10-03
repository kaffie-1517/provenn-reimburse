import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(StrEnum):
    PROVIDER = "provider"
    EMPLOYEE = "employee"
    COMPANY_ADMIN = "company_admin"
    PLATFORM_ADMIN = "platform_admin"


TENANT_ROLES = {Role.EMPLOYEE, Role.COMPANY_ADMIN}


class InvoiceStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"


class Result(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    NOT_FOUND = "not_found"


class Approval(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def _in(col: str, enum: type[StrEnum]) -> str:
    return f"{col} IN ({', '.join(repr(e.value) for e in enum)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), unique=True)
    plan: Mapped[str] = mapped_column(String(32), default="starter")
    # Shared with employees so they can join this company at sign-up.
    join_code: Mapped[str] = mapped_column(String(12), unique=True)
    created_at: Mapped[datetime] = _created()


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), unique=True)
    # Keys look like pk_<prefix>.<secret>; we look up by prefix, bcrypt the secret.
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True)
    key_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", Role), name="ck_users_role"),
        # Tenant roles always belong to a company; the others never do.
        CheckConstraint(
            "(role IN ('employee', 'company_admin')) = (company_id IS NOT NULL)",
            name="ck_users_tenant",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    # A person's name, or the business name for vendor accounts.
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(32))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    created_at: Mapped[datetime] = _created()

    company: Mapped[Company | None] = relationship(lazy="joined")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(_in("status", InvoiceStatus), name="ck_invoices_status"),
        CheckConstraint("amount_cents > 0", name="ck_invoices_amount"),
        CheckConstraint(
            "(partner_id IS NULL) <> (provider_user_id IS NULL)", name="ck_invoices_issuer"
        ),
        Index("ix_invoices_provider_created", "provider_user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    reference_code: Mapped[str] = mapped_column(String(8), unique=True)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("partners.id"))
    provider_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    vendor_name: Mapped[str] = mapped_column(String(200))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    invoice_date: Mapped[date] = mapped_column(Date)
    purchase_ref: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default=InvoiceStatus.PROCESSING)
    created_at: Mapped[datetime] = _created()

    versions: Mapped[list["InvoiceVersion"]] = relationship(
        back_populates="invoice", order_by="InvoiceVersion.version_number"
    )


class InvoiceVersion(Base):
    __tablename__ = "invoice_versions"
    __table_args__ = (UniqueConstraint("invoice_id", "version_number"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    sha256_hash: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = _created()

    invoice: Mapped[Invoice] = relationship(back_populates="versions")


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    billed_at: Mapped[datetime] = _created()


class Verification(Base):
    __tablename__ = "verifications"
    __table_args__ = (
        CheckConstraint(_in("result", Result), name="ck_verifications_result"),
        CheckConstraint(_in("approval_status", Approval), name="ck_verifications_approval"),
        Index("ix_verifications_company_submitted", "company_id", "submitted_at"),
        Index("ix_verifications_company_approval", "company_id", "approval_status"),
        Index("ix_verifications_user_submitted", "submitted_by", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    extracted_code: Mapped[str | None] = mapped_column(String(8))
    submitted_hash: Mapped[str] = mapped_column(String(64))
    matched_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoice_versions.id"))
    file_name: Mapped[str | None] = mapped_column(String(255))
    result: Mapped[str] = mapped_column(String(16))
    approval_status: Mapped[str] = mapped_column(String(16), default=Approval.PENDING)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = _created()

    submitter: Mapped[User] = relationship(foreign_keys=[submitted_by], lazy="joined")
    invoice: Mapped[Invoice | None] = relationship(lazy="joined")


class Job(Base):
    """A row in the Postgres-backed job queue (see app/jobs.py)."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("state IN ('queued', 'running', 'done', 'failed')", name="ck_jobs_state"),
        Index(
            "ix_jobs_ready",
            "run_at",
            postgresql_where="state = 'queued'",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
