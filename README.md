<div align="center">

# ProveNN Reimburse

**Tamper-evident invoices for expense reimbursement.**

Fingerprint every invoice when it's issued. Catch edited copies before anyone approves them.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![Tests](https://img.shields.io/badge/tests-37%20passing-56653a)

</div>

---

## The problem

Expense fraud is usually low-tech: an employee downloads a genuine invoice, edits the amount
in a PDF editor, and submits it. The edited file looks identical, so finance teams approve it.
Nothing in a typical reimbursement flow checks that the submitted file is the one the vendor
actually issued.

## How ProveNN solves it

```
  Vendor issues            Buyer downloads            Employee submits
 ┌──────────────┐        ┌─────────────────┐        ┌──────────────────────┐
 │ invoice.pdf  │──────▶ │ stamped PDF     │──────▶ │ sha256(file)         │
 │              │ stamp  │ PNN-7Q4MZK2D    │        │   == issued hash ?   │
 │ sha256 → DB  │  + QR  │ + QR code       │        │ match / mismatch     │
 └──────────────┘        └─────────────────┘        └──────────────────────┘
```

1. **Issue.** A vendor uploads an invoice, or their billing system sends it over the API.
   A background worker stamps a reference code (`PNN-XXXXXXXX`) and a QR code onto every page,
   then records the SHA-256 of the final file.
2. **Share.** The buyer downloads the stamped PDF from a public link. That exact file is the
   only copy that will verify.
3. **Verify.** When an employee submits the invoice for reimbursement, ProveNN reads the
   reference code (from a marker, the page text, or the QR image), hashes the file and compares
   it with the issued version. **One changed byte → `mismatch`.**
4. **Approve.** Finance reviews a queue where every claim already carries its check result,
   approves or rejects, and exports approved claims to Excel for the ERP.

## Features

| Role | What they can do |
|---|---|
| **Vendor** (`provider`) | Issue invoices from the portal, track stamping and downloads |
| **Billing partner** | Issue invoices server-to-server with an `X-Partner-Key` |
| **Employee** | Upload an invoice, get an instant verdict, follow claim status |
| **Finance** (`company_admin`) | Review queue, approve/reject, export approved claims to `.xlsx`, invite employees with a join code |
| **Platform admin** | Cross-tenant usage: invoices, billed downloads, claims and mismatch rate per company |
| **Anyone** | Look up an invoice by reference code and download the original |

**Under the hood:**

- **Strict multi-tenancy.** The company is taken from the signed token, never from the request.
  Another company's claim returns `404`, not `403`, so IDs don't leak.
- **Postgres job queue.** No Redis or SQS. Jobs are enqueued in the same transaction as the
  invoice and claimed with `FOR UPDATE SKIP LOCKED`, with exponential backoff and recovery of
  stale jobs.
- **Idempotent billing.** The first download writes exactly one billing event, even under
  concurrent requests, enforced by a unique key.
- **Resilient stamping.** Encrypted or malformed PDFs are still issued, carrying a trailing
  `% REF:` marker that keeps the file valid for strict PDF readers.
- **Observability.** Prometheus metrics labelled by route template (bounded cardinality),
  queue depth and job outcomes, plus a provisioned Grafana dashboard.

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI, Pydantic v2 |
| Database | PostgreSQL, SQLAlchemy 2.0 (async, asyncpg), Alembic |
| Jobs | Postgres-backed queue + worker (`python -m app.worker`) |
| PDFs | pypdf, ReportLab, qrcode, zxing-cpp |
| Auth | JWT (PyJWT), bcrypt, prefixed partner API keys |
| Storage | Any S3-compatible store (MinIO, AWS S3, Cloudflare R2, Supabase) or local disk |
| Exports | openpyxl |
| Metrics | prometheus-client, Grafana |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, CSS Modules |
| Tooling | uv, Ruff, pytest, ESLint |

## Architecture

```
                ┌─────────────────────────┐
  Browser ────▶ │  Next.js (web/)         │
                └───────────┬─────────────┘
                            │ JSON / multipart
                ┌───────────▼─────────────┐        ┌──────────────────┐
  Partner ────▶ │  FastAPI (api)          │──────▶ │ Object storage   │
  (API key)     │  auth · invoices ·      │        │ raw + stamped PDF│
                │  verifications · admin  │        └────────▲─────────┘
                └───────────┬─────────────┘                 │
                            │ rows + jobs (same txn)        │
                ┌───────────▼─────────────┐        ┌────────┴─────────┐
                │  PostgreSQL             │◀──────▶│  Worker          │
                │  data + jobs queue      │ claim  │  stamp + hash    │
                └─────────────────────────┘        └──────────────────┘
```

The API and worker share one codebase. For single-instance hosting, `RUN_WORKER=true`
runs the worker loop inside the API process.

## Getting started

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20+, and Docker
for local Postgres/MinIO. Any Postgres you already run works too.

```bash
git clone https://github.com/kaffie-1517/provenn-reimburse.git
cd provenn-reimburse

make infra      # postgres, minio, prometheus, grafana
make install    # backend + frontend dependencies
make migrate    # apply database migrations
make seed       # demo companies, users, a partner key and sample activity
```

Run each in its own terminal:

```bash
make api        # http://localhost:8000  (OpenAPI docs at /docs)
make worker     # stamps issued invoices
make web        # http://localhost:3000
```

**Demo accounts** (password `password`). The seed creates two fictional employers, their
people, airline/hotel vendors and two ride-app billing partners, with a month of claims
including two forged invoices.

| Role | Name | Email |
|---|---|---|
| Finance · Northstar Technologies | Priya Sharma | `priya.sharma@northstar.demo` |
| Employee · Northstar Technologies | Rohan Mehta | `rohan.mehta@northstar.demo` |
| Employee · Northstar Technologies | Aisha Khan | `aisha.khan@northstar.demo` |
| Finance · Kavya Retail | Vikram Rao | `vikram.rao@kavyaretail.demo` |
| Employee · Kavya Retail | Ananya Iyer | `ananya.iyer@kavyaretail.demo` |
| Vendor | Air India | `billing@airindia.demo` |
| Vendor | IndiGo | `billing@goindigo.demo` |
| Vendor | Taj Hotels | `billing@tajhotels.demo` |
| Platform admin | Platform Ops | `ops@provenn.demo` |

Employees join with the company code `NORTHSTAR` or `KAVYARETAIL`. Uber India and Rapido
are API partners; `make seed` prints their keys once.

To show one-click demo logins on the sign-in page, set `NEXT_PUBLIC_DEMO_PASSWORD=password`
in `web/.env.local`.

**Try the partner API** with one of the printed keys:

```bash
make demo KEY=pk_xxxxxxxxxx.your-secret
```

### Without Docker

Point the backend at any Postgres and store PDFs on disk:

```bash
# backend/.env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/provenn
STORAGE_DIR=./data
```

## Configuration

Backend settings come from environment variables or `backend/.env`
(see [`backend/.env.example`](backend/.env.example)).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local Postgres | `postgres://` and `?sslmode=` URLs are accepted as-is |
| `JWT_SECRET` | dev value | **Required in production** (32+ chars) |
| `APP_ENV` | `development` | `production` enables startup safety checks |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated web origins |
| `PUBLIC_WEB_URL` | — | When set, QR codes link to the invoice page |
| `STORAGE_DIR` | — | Store PDFs on local disk instead of S3 |
| `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET` | MinIO | Any S3-compatible store |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | MinIO | Leave empty on AWS to use the instance role |
| `RUN_WORKER` | `false` | Run the job worker inside the API process |
| `MAX_UPLOAD_MB` | `20` | Upload limit for PDFs |

The frontend reads `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## API overview

Full interactive docs are served at `/docs`.

| Method | Path | Auth | |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` · `/login` | — | Create account / sign in |
| `GET` | `/api/v1/auth/me` | JWT | Current user |
| `POST` | `/api/v1/invoices` | provider | Issue an invoice (multipart) |
| `POST` | `/api/v1/partner/invoices` | `X-Partner-Key` | Issue as a billing partner |
| `GET` | `/api/v1/invoices/mine` | provider | Issued invoices |
| `GET` | `/api/v1/invoices/{code}` | — | Public status |
| `GET` | `/api/v1/invoices/{code}/download` | — | Stamped PDF (bills once) |
| `POST` | `/api/v1/verifications` | employee | Submit a claim |
| `GET` | `/api/v1/verifications` | employee, finance | Claims, scoped and filterable |
| `PATCH` | `/api/v1/verifications/{id}` | finance | Approve or reject |
| `GET` | `/api/v1/verifications/export` | finance | Approved claims as `.xlsx` |
| `GET` | `/api/v1/admin/partners` · `/companies` | platform admin | Usage reports |
| `GET` | `/healthz` · `/metrics` | — | Health, Prometheus |

Issuing an invoice as a partner:

```bash
curl -X POST http://localhost:8000/api/v1/partner/invoices \
  -H "X-Partner-Key: $PARTNER_KEY" \
  -F pdf=@invoice.pdf \
  -F vendor_name="Uber India" \
  -F amount_cents=74250 -F currency=INR -F invoice_date=2026-10-01
# → 202 {"invoice_id": "...", "reference_code": "7Q4MZK2D", "status": "processing"}
```

## Testing

Tests run against a real Postgres, because the queue and the constraints are part of
the behaviour under test.

```bash
createdb -h localhost -U provenn provenn_test   # password: provenn (docker compose)
make test     # or: TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest
make lint
```

Coverage includes PDF stamp/extract round-trips (marker, text and QR), tamper detection,
tenancy isolation, role guards, concurrent claiming in the job queue, retry and backoff,
idempotent billing under concurrent downloads, Excel export contents and usage reports.

## Project structure

```
backend/
  app/
    main.py            app factory, middleware, routers
    models.py          tables and check constraints
    routers/           auth · invoices · verifications · admin
    pdf.py             stamp, marker, hash, code extraction
    jobs.py            Postgres job queue
    worker.py          job runner + stamp handler
    reports.py         the only cross-tenant queries
    security.py        hashing, JWT, partner keys
    storage.py         S3 / local disk / in-memory
    seed.py            demo data
  migrations/          Alembic
  tests/
web/
  app/                 landing, auth, /i/[code], provider, claims, review, console
  components/          shell, table, file drop, UI primitives, theme
  lib/                 API client, auth, formatting
deploy/                Prometheus + Grafana provisioning
render.yaml            Render blueprint (API + in-process worker)
docker-compose.yml     local infrastructure
```

## Deployment

The app runs comfortably on free tiers: the **frontend** on Vercel (root `web/`), the **API**
on Render using the included [`render.yaml`](render.yaml) blueprint, with `RUN_WORKER=true`,
and **Postgres + storage** on Supabase, Neon + R2, or AWS RDS + S3.

Set `APP_ENV=production`, a strong `JWT_SECRET`, `CORS_ORIGINS` for the web origin and
`NEXT_PUBLIC_API_URL` for the API origin. Migrations run on every API start.

## Roadmap

- Duplicate-claim detection (the same invoice claimed twice)
- Invoice amendments as new versions with an audit trail
- Webhooks to partners when an invoice is downloaded or verified
- Email notifications for finance on new mismatches
