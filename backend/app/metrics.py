import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

JOBS_PROCESSED = Counter("jobs_processed_total", "Jobs finished", ["kind", "outcome"])
JOB_DURATION = Histogram("job_duration_seconds", "Job run time", ["kind"])
QUEUE_DEPTH = Gauge("jobs_queue_depth", "Jobs waiting to run")

INVOICES_ISSUED = Counter("invoices_issued_total", "Invoices issued", ["source"])
VERIFICATIONS = Counter("verifications_total", "Verification results", ["result"])
DOWNLOADS_BILLED = Counter("downloads_billed_total", "First downloads that created a bill")


class MetricsMiddleware:
    """Records count + latency per route *template* (/invoices/{code}), so
    reference codes and ids never become label values."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", None) or "unmatched"
            method = scope["method"]
            HTTP_REQUESTS.labels(method, template, str(status)).inc()
            HTTP_LATENCY.labels(method, template).observe(time.perf_counter() - start)
