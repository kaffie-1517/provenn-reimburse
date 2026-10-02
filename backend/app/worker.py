"""Background worker: claims jobs from Postgres and runs their handlers.

Run standalone with `python -m app.worker`, or inside the api process with
RUN_WORKER=true (see app.main).
"""

import asyncio
import contextlib
import logging
import signal
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from prometheus_client import start_http_server
from sqlalchemy.ext.asyncio import AsyncSession

from app import db, jobs, metrics, pdf
from app.config import get_settings
from app.models import Invoice, InvoiceStatus, InvoiceVersion
from app.storage import Storage, get_storage, raw_key, version_key

log = logging.getLogger("provenn.worker")

STAMP_INVOICE = "stamp_invoice"

Handler = Callable[[AsyncSession, Storage, dict[str, Any]], Awaitable[None]]


async def stamp_invoice(session: AsyncSession, storage: Storage, payload: dict[str, Any]) -> None:
    """raw.pdf -> stamped + marked v1.pdf, records its hash, marks invoice ready.

    Idempotent: if a previous attempt already finished, it does nothing.
    """
    invoice = await session.get(Invoice, uuid.UUID(payload["invoice_id"]))
    if invoice is None:
        raise LookupError(f"invoice {payload['invoice_id']} not found")
    if invoice.status == InvoiceStatus.READY:
        return

    raw = await storage.get(raw_key(invoice.id))
    base = get_settings().public_web_url
    qr_payload = f"{base.rstrip('/')}/i/{invoice.reference_code}" if base else None
    try:
        stamped = await asyncio.to_thread(pdf.stamp, raw, invoice.reference_code, qr_payload)
    except pdf.StampError as e:
        # Still issue it: the marker alone is enough for verification.
        log.warning("invoice %s issued unstamped: %s", invoice.reference_code, e)
        stamped = raw
    final = pdf.with_marker(stamped, invoice.reference_code)

    key = version_key(invoice.id, 1)
    await storage.put(key, final)
    session.add(
        InvoiceVersion(
            invoice_id=invoice.id, version_number=1, sha256_hash=pdf.sha256(final), storage_key=key
        )
    )
    invoice.status = InvoiceStatus.READY
    await session.commit()


HANDLERS: dict[str, Handler] = {STAMP_INVOICE: stamp_invoice}


async def run_once(storage: Storage) -> bool:
    """Runs at most one job. Returns False when the queue was empty."""
    async with db.sessionmaker()() as session:
        job = await jobs.claim(session)
        if job is None:
            return False

        kind = job.kind
        handler = HANDLERS.get(kind)
        start = time.perf_counter()
        try:
            if handler is None:
                raise LookupError(f"no handler for job kind {kind!r}")
            async with db.sessionmaker()() as work:
                await handler(work, storage, job.payload)
        except Exception as e:
            gave_up = await jobs.fail(session, job, f"{type(e).__name__}: {e}")
            metrics.JOBS_PROCESSED.labels(kind, "failed" if gave_up else "retry").inc()
            log.exception("job %s (%s) failed, attempt %s", job.id, kind, job.attempts)
        else:
            await jobs.complete(session, job)
            metrics.JOBS_PROCESSED.labels(kind, "ok").inc()
        finally:
            metrics.JOB_DURATION.labels(kind).observe(time.perf_counter() - start)
        return True


async def drain(storage: Storage | None = None) -> int:
    """Runs jobs until the queue is empty. Used by tests and the seed command."""
    storage = storage or get_storage()
    n = 0
    while await run_once(storage):
        n += 1
    return n


async def run_forever(stop: asyncio.Event, storage: Storage | None = None) -> None:
    storage = storage or get_storage()
    poll = get_settings().worker_poll_seconds
    last_housekeeping = 0.0
    log.info("worker started")
    while not stop.is_set():
        try:
            if time.monotonic() - last_housekeeping > 30:
                async with db.sessionmaker()() as s:
                    if n := await jobs.requeue_stale(s):
                        log.warning("requeued %s stale jobs", n)
                    metrics.QUEUE_DEPTH.set(await jobs.depth(s))
                last_housekeeping = time.monotonic()
            if await run_once(storage):
                continue  # more work may be waiting; don't sleep
        except Exception:
            log.exception("worker loop error")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=poll)
    log.info("worker stopped")


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    start_http_server(get_settings().worker_metrics_port)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await run_forever(stop)
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
