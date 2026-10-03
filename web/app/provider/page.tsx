"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { FileDrop } from "@/components/file-drop";
import { Shell, ShellPlaceholder } from "@/components/shell";
import { Button, Copy, Empty, Field, Notice, Skeleton, Status } from "@/components/ui";
import t from "@/components/table.module.css";
import { api, ApiError, type InvoiceRow } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { ago, date, money, refDisplay, toCents } from "@/lib/format";
import s from "./provider.module.css";

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD"];
/** Local calendar date as YYYY-MM-DD (toISOString would give the UTC date). */
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

interface Issued {
  reference_code: string;
}

function IssueForm({ token, onIssued }: { token: string; onIssued: (code: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [vendor, setVendor] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [invoiceDate, setInvoiceDate] = useState(today);
  const [purchaseRef, setPurchaseRef] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const cents = toCents(amount);
    if (cents === null) {
      setAmountError("Enter an amount like 1500 or 1,500.50");
      return;
    }
    if (!file) {
      setError("Attach the invoice PDF.");
      return;
    }
    const form = new FormData();
    form.append("pdf", file);
    form.append("vendor_name", vendor);
    form.append("amount_cents", String(cents));
    form.append("currency", currency);
    form.append("invoice_date", invoiceDate);
    if (purchaseRef.trim()) form.append("purchase_ref", purchaseRef.trim());

    setBusy(true);
    try {
      const issued = await api<Issued>("/api/v1/invoices", { token, form });
      onIssued(issued.reference_code);
      setFile(null);
      setVendor("");
      setAmount("");
      setPurchaseRef("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't issue the invoice.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={s.form} onSubmit={submit} aria-labelledby="new-invoice">
      <h2 id="new-invoice" className={s.panelTitle}>
        New invoice
      </h2>
      {error && <Notice tone="error">{error}</Notice>}
      <FileDrop file={file} onFile={setFile} compact disabled={busy} />
      <Field
        label="Vendor name"
        hint="As printed on the invoice."
        required
        maxLength={200}
        value={vendor}
        onChange={(e) => setVendor(e.target.value)}
        placeholder="Air India"
      />
      <div className={s.amountRow}>
        <Field
          label="Amount"
          required
          inputMode="decimal"
          value={amount}
          error={amountError}
          onChange={(e) => {
            setAmount(e.target.value);
            setAmountError(null);
          }}
          placeholder="0.00"
          className={s.amount}
        />
        <div className={s.selectField}>
          <label htmlFor="currency" className={s.selectLabel}>
            Currency
          </label>
          <select
            id="currency"
            className={s.select}
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {CURRENCIES.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>
      <Field
        label="Invoice date"
        type="date"
        required
        max={today()}
        value={invoiceDate}
        onChange={(e) => setInvoiceDate(e.target.value)}
      />
      <Field
        label="Purchase reference"
        optional
        maxLength={100}
        value={purchaseRef}
        onChange={(e) => setPurchaseRef(e.target.value)}
        placeholder="PO-2026-118"
      />
      <Button variant="primary" type="submit" loading={busy} className={s.submit}>
        Issue invoice
      </Button>
    </form>
  );
}

function InvoiceTable({ rows }: { rows: InvoiceRow[] | null }) {
  if (rows === null) {
    return (
      <div className={t.wrap} aria-busy="true">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className={s.skeletonRow}>
            <Skeleton width="22%" />
            <Skeleton width="30%" />
            <Skeleton width="16%" />
          </div>
        ))}
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className={t.wrap}>
        <Empty title="No invoices yet">
          Issue your first invoice with the form. It&apos;s stamped and ready to share in a few
          seconds.
        </Empty>
      </div>
    );
  }
  return (
    <div className={t.wrap}>
      <div className={t.scroll}>
        <table className={t.table}>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Vendor</th>
              <th className={t.right}>Amount</th>
              <th className={t.hideSm}>Invoice date</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <Link href={`/i/${r.reference_code}`} className={t.codeLink}>
                    {refDisplay(r.reference_code)}
                  </Link>
                </td>
                <td className={t.truncate}>
                  <span className={t.primaryCell}>{r.vendor_name}</span>
                  {r.purchase_ref && <span className={t.sub}>{r.purchase_ref}</span>}
                </td>
                <td className={t.right}>{money(r.amount_cents, r.currency)}</td>
                <td className={`${t.muted} ${t.nowrap} ${t.hideSm}`}>{date(r.invoice_date)}</td>
                <td className={t.nowrap}>
                  {!r.ready ? (
                    <Status tone="warn" pulse>
                      Stamping
                    </Status>
                  ) : r.downloaded ? (
                    <Status tone="ok">Downloaded</Status>
                  ) : (
                    <Status tone="muted">Ready · {ago(r.issued_at)}</Status>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ProviderPage() {
  const session = useRequireRole("provider");
  const token = session?.token;
  const [rows, setRows] = useState<InvoiceRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [justIssued, setJustIssued] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setRows(await api<InvoiceRow[]>("/api/v1/invoices/mine", { token }));
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Couldn't load invoices");
    }
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch
    load();
  }, [load]);

  const stamping = rows?.some((r) => !r.ready);
  useEffect(() => {
    if (!stamping) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [stamping, load]);

  if (!session) return <ShellPlaceholder />;

  return (
    <Shell
      title="Invoices"
      description="Each invoice is stamped with a reference code and fingerprinted when you issue it."
    >
      <div className={s.layout}>
        <section className={s.panel}>
          <IssueForm
            token={session.token}
            onIssued={(code) => {
              setJustIssued(code);
              load();
            }}
          />
        </section>

        <section className={s.list} aria-labelledby="issued">
          <div className={s.listHead}>
            <h2 id="issued" className={s.panelTitle}>
              Issued
            </h2>
            {rows && rows.length > 0 && <span className={s.count}>{rows.length}</span>}
          </div>
          {justIssued && (
            <Notice
              tone="success"
              action={
                <Button size="sm" variant="ghost" onClick={() => setJustIssued(null)}>
                  Dismiss
                </Button>
              }
            >
              Issued <Copy text={refDisplay(justIssued)} />. Share the link{" "}
              <Link href={`/i/${justIssued}`}>/i/{justIssued}</Link> with your customer.
            </Notice>
          )}
          {loadError && (
            <Notice tone="error" action={<Button size="sm" onClick={load}>Retry</Button>}>
              {loadError}
            </Notice>
          )}
          <InvoiceTable rows={rows} />
        </section>
      </div>
    </Shell>
  );
}
