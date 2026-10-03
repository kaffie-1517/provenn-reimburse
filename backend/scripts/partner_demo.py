"""Issues an invoice through the partner API, waits for it, downloads it.

uv run python scripts/partner_demo.py pk_xxxxxxxxxx.secret [--api http://localhost:8000]
"""

import argparse
import io
import time
from datetime import date
from pathlib import Path

import httpx
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def sample_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 760, "Uber India — Trip Receipt")
    c.setFont("Helvetica", 12)
    c.drawString(72, 730, "Airport to Cyber City, UberGo: INR 742.50")
    c.showPage()
    c.save()
    return buf.getvalue()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("key", help="partner API key printed by the seed command")
    p.add_argument("--api", default="http://localhost:8000")
    args = p.parse_args()

    with httpx.Client(base_url=args.api, timeout=30) as http:
        r = http.post(
            "/api/v1/partner/invoices",
            headers={"X-Partner-Key": args.key},
            data={
                "vendor_name": "Uber India",
                "amount_cents": 74_250,
                "currency": "INR",
                "invoice_date": date.today().isoformat(),
                "purchase_ref": "UBR-8K2N4T90",
            },
            files={"pdf": ("invoice.pdf", sample_pdf(), "application/pdf")},
        )
        r.raise_for_status()
        code = r.json()["reference_code"]
        print(f"issued   PNN-{code}")

        for _ in range(30):
            if http.get(f"/api/v1/invoices/{code}").json()["ready"]:
                break
            time.sleep(1)
        else:
            raise SystemExit("not ready after 30s — is the worker running?")
        print("stamped  ready")

        pdf = http.get(f"/api/v1/invoices/{code}/download")
        pdf.raise_for_status()
        out = f"invoice-PNN-{code}.pdf"
        Path(out).write_bytes(pdf.content)
        print(f"saved    {out} ({len(pdf.content):,} bytes)")


if __name__ == "__main__":
    main()
