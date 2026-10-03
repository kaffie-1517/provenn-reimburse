import asyncio
import uuid
from datetime import date

from sqlalchemy import select, text

from app import db, jobs, pdf, worker
from app.models import Invoice, InvoiceVersion, Job, User
from app.storage import MemoryStorage, raw_key
from tests.pdfs import invoice_pdf


async def _enqueue(n: int = 1, kind: str = "noop") -> None:
    async with db.sessionmaker()() as s:
        for i in range(n):
            jobs.enqueue(s, kind, {"i": i})
        await s.commit()


async def test_claim_is_fifo_and_exclusive():
    await _enqueue(5)
    sm = db.sessionmaker()
    sessions = [sm() for _ in range(5)]
    claimed = await asyncio.gather(*(jobs.claim(s) for s in sessions))
    ids = [j.id for j in claimed]
    assert sorted(ids) == [1, 2, 3, 4, 5]  # every job once, none twice
    for s in sessions:
        await s.close()
    async with sm() as s:
        assert await jobs.claim(s) is None


async def test_failure_backs_off_then_gives_up():
    await _enqueue(1)
    async with db.sessionmaker()() as s:
        job = await jobs.claim(s)
        job.max_attempts = 2
        assert await jobs.fail(s, job, "boom") is False
        await s.refresh(job)
        assert job.state == "queued" and job.last_error == "boom"
        assert await jobs.claim(s) is None  # backoff: not runnable yet

        await s.execute(text("UPDATE jobs SET run_at = now()"))
        job = await jobs.claim(s)
        assert job.attempts == 2
        assert await jobs.fail(s, job, "boom again") is True
        await s.refresh(job)
        assert job.state == "failed"


async def test_stale_running_jobs_are_requeued():
    await _enqueue(1)
    async with db.sessionmaker()() as s:
        await jobs.claim(s)
        await s.execute(text("UPDATE jobs SET locked_at = now() - interval '1 hour'"))
        await s.commit()
        assert await jobs.requeue_stale(s) == 1
        assert await jobs.depth(s) == 1


async def test_unknown_kind_fails_without_crashing_worker():
    await _enqueue(1, kind="does_not_exist")
    assert await worker.run_once(MemoryStorage()) is True
    async with db.sessionmaker()() as s:
        job = await s.scalar(select(Job))
        assert job.state == "queued" and "no handler" in job.last_error


async def test_stamp_invoice_job():
    store = MemoryStorage()
    async with db.sessionmaker()() as s:
        provider = User(name="Air India", email="p@example.com", password_hash="x", role="provider")
        s.add(provider)
        await s.flush()
        inv = Invoice(
            reference_code="ABCD2345",
            provider_user_id=provider.id,
            vendor_name="Acme",
            amount_cents=150000,
            currency="INR",
            invoice_date=date(2026, 9, 1),
        )
        s.add(inv)
        await s.flush()
        await store.put(raw_key(inv.id), invoice_pdf())
        jobs.enqueue(s, worker.STAMP_INVOICE, {"invoice_id": str(inv.id)})
        await s.commit()
        inv_id = inv.id

    assert await worker.drain(store) == 1

    async with db.sessionmaker()() as s:
        inv = await s.get(Invoice, inv_id)
        assert inv.status == "ready"
        version = await s.scalar(select(InvoiceVersion).where(InvoiceVersion.invoice_id == inv_id))
        stored = store.objects[version.storage_key]
        assert pdf.sha256(stored) == version.sha256_hash
        assert pdf.find_code(stored) == "ABCD2345"
        assert (await s.scalar(select(Job))).state == "done"

    # Running the same job again must not create a second version.
    async with db.sessionmaker()() as s:
        await worker.stamp_invoice(s, store, {"invoice_id": str(inv_id)})
        n = await s.scalar(text("SELECT count(*) FROM invoice_versions"))
        assert n == 1


async def test_missing_invoice_is_a_job_failure():
    async with db.sessionmaker()() as s:
        jobs.enqueue(s, worker.STAMP_INVOICE, {"invoice_id": str(uuid.uuid4())})
        await s.commit()
    await worker.drain(MemoryStorage())
    async with db.sessionmaker()() as s:
        assert "not found" in (await s.scalar(select(Job))).last_error
