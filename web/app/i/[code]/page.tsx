"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ThemeToggle } from "@/components/theme";
import { Button, ButtonLink, Empty, Logo, Notice, Skeleton, Status } from "@/components/ui";
import { api, ApiError, download, type InvoicePublic } from "@/lib/api";
import { date, dateTime, money, parseRef, refDisplay } from "@/lib/format";
import s from "./invoice.module.css";

type State =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error"; message: string }
  | { kind: "ok"; invoice: InvoicePublic };

export default function InvoicePage() {
  const params = useParams<{ code: string }>();
  const code = parseRef(params.code ?? "");
  const [state, setState] = useState<State>(code ? { kind: "loading" } : { kind: "missing" });
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!code) return;
    try {
      const invoice = await api<InvoicePublic>(`/api/v1/invoices/${code}`);
      setState({ kind: "ok", invoice });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setState({ kind: "missing" });
      else setState({ kind: "error", message: e instanceof Error ? e.message : "Couldn't load" });
    }
  }, [code]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch
    load();
  }, [load]);

  // While the stamp job runs, poll quietly.
  const processing = state.kind === "ok" && !state.invoice.ready;
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [processing, load]);

  async function getPdf() {
    if (!code) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const r = await download(`/api/v1/invoices/${code}/download`);
      if (r.status === 202) load();
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className={s.page}>
      <header className={s.top}>
        <Logo />
        <ThemeToggle />
      </header>

      <main className={s.main}>
        {state.kind === "loading" && (
          <div className={s.doc} aria-busy="true">
            <Skeleton width="40%" />
            <div className={s.skeletonRows}>
              {[60, 45, 50, 35].map((w) => (
                <Skeleton key={w} width={`${w}%`} />
              ))}
            </div>
          </div>
        )}

        {state.kind === "missing" && (
          <Empty
            title="No invoice with that reference code"
            action={<ButtonLink href="/">Try another code</ButtonLink>}
          >
            Check the code printed next to the QR on the invoice. It looks like PNN-7Q4MZK2D.
          </Empty>
        )}

        {state.kind === "error" && (
          <Notice tone="error" action={<Button size="sm" onClick={load}>Retry</Button>}>
            {state.message}
          </Notice>
        )}

        {state.kind === "ok" && (
          <article className={s.doc}>
            <div className={s.head}>
              <p className={s.kicker}>Invoice</p>
              <h1 className={`${s.code} mono`}>{refDisplay(state.invoice.reference_code)}</h1>
              {state.invoice.ready ? (
                <Status tone="ok">Issued and sealed</Status>
              ) : (
                <Status tone="warn" pulse>
                  Preparing the stamped copy…
                </Status>
              )}
            </div>

            <dl className={s.details}>
              <div>
                <dt>Vendor</dt>
                <dd>{state.invoice.vendor_name}</dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd className="num">{money(state.invoice.amount_cents, state.invoice.currency)}</dd>
              </div>
              <div>
                <dt>Invoice date</dt>
                <dd>{date(state.invoice.invoice_date)}</dd>
              </div>
              <div>
                <dt>Issued on ProveNN</dt>
                <dd>{dateTime(state.invoice.issued_at)}</dd>
              </div>
            </dl>

            <div className={s.action}>
              <Button
                variant="primary"
                onClick={getPdf}
                loading={downloading}
                disabled={!state.invoice.ready}
              >
                Download PDF
              </Button>
              <p className={s.note}>
                This is the original as issued. Submit this exact file for reimbursement — any
                change to it, even re-saving, will show up as a mismatch.
              </p>
            </div>
            {downloadError && <Notice tone="error">{downloadError}</Notice>}
          </article>
        )}
      </main>
    </div>
  );
}
