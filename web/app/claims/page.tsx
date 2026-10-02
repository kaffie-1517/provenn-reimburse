"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FileDrop } from "@/components/file-drop";
import { Shell, ShellPlaceholder } from "@/components/shell";
import {
  ApprovalStatus,
  Button,
  Empty,
  Notice,
  ResultStatus,
  Segmented,
  Skeleton,
} from "@/components/ui";
import t from "@/components/table.module.css";
import { api, ApiError, type Page, type Result, type Verification } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { ago, money, refDisplay, shortHash } from "@/lib/format";
import s from "./claims.module.css";

const VERDICT: Record<Result, { title: string; body: (v: Verification) => string }> = {
  match: {
    title: "Verified",
    body: (v) =>
      `This is exactly the invoice ${v.invoice?.vendor_name ?? "the vendor"} issued. It's now with your finance team for approval.`,
  },
  mismatch: {
    title: "This file was changed after it was issued",
    body: (v) =>
      `The reference code ${v.extracted_code ? refDisplay(v.extracted_code) : ""} is real, but the file doesn't match the original. Download the original from the vendor's link and submit that instead.`,
  },
  not_found: {
    title: "Not a ProveNN invoice",
    body: () =>
      "We couldn't find a ProveNN reference code in this file. Ask the vendor for the stamped copy — it has a QR code and a PNN- reference.",
  },
};

function Verdict({ v }: { v: Verification }) {
  const verdict = VERDICT[v.result];
  return (
    <div className={s.verdict} data-result={v.result} role="status">
      <div className={s.verdictHead}>
        <ResultStatus result={v.result} />
        <span className={s.verdictFile}>{v.file_name}</span>
      </div>
      <p className={s.verdictTitle}>{verdict.title}</p>
      <p className={s.verdictBody}>{verdict.body(v)}</p>
      {v.invoice && (
        <dl className={s.verdictFacts}>
          <div>
            <dt>Invoice</dt>
            <dd>
              <Link href={`/i/${v.invoice.reference_code}`} className="mono">
                {refDisplay(v.invoice.reference_code)}
              </Link>
            </dd>
          </div>
          <div>
            <dt>Amount</dt>
            <dd className="num">{money(v.invoice.amount_cents, v.invoice.currency)}</dd>
          </div>
          <div>
            <dt>Fingerprint</dt>
            <dd className="mono">{shortHash(v.submitted_hash)}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

function Submit({ token, onDone }: { token: string; onDone: (v: Verification) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("pdf", file);
    try {
      onDone(await api<Verification>("/api/v1/verifications", { token, form }));
      setFile(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={s.submit}>
      <FileDrop file={file} onFile={setFile} label="Invoice to claim" disabled={busy} />
      {error && <Notice tone="error">{error}</Notice>}
      <Button variant="primary" onClick={send} disabled={!file} loading={busy}>
        {busy ? "Checking…" : "Submit for reimbursement"}
      </Button>
    </div>
  );
}

type Filter = "all" | "pending" | "approved" | "rejected";

export default function ClaimsPage() {
  const session = useRequireRole("employee");
  const token = session?.token;
  const [last, setLast] = useState<Verification | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [data, setData] = useState<Page<Verification> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    const q = filter === "all" ? "" : `&approval_status=${filter}`;
    try {
      setData(await api<Page<Verification>>(`/api/v1/verifications?limit=100${q}`, { token }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load your claims");
    }
  }, [token, filter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on filter change
    load();
  }, [load]);

  if (!session) return <ShellPlaceholder />;

  return (
    <Shell
      title="Claims"
      description="Upload the invoice you received. We check it against the original before it reaches finance."
    >
      <section className={s.top}>
        <Submit
          token={session.token}
          onDone={(v) => {
            setLast(v);
            load();
          }}
        />
        {last ? (
          <Verdict v={last} />
        ) : (
          <div className={s.guide}>
            <p className={s.guideTitle}>What gets checked</p>
            <ol className={s.guideList}>
              <li>We read the PNN- reference from the stamp, text or QR code.</li>
              <li>We fingerprint your file and compare it with the one the vendor issued.</li>
              <li>A match goes to your finance team; anything else is flagged.</li>
            </ol>
          </div>
        )}
      </section>

      <section className={s.history} aria-labelledby="history">
        <div className={s.historyHead}>
          <h2 id="history" className={s.sectionTitle}>
            Your claims
          </h2>
          <Segmented
            label="Filter claims"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All" },
              { value: "pending", label: "Pending" },
              { value: "approved", label: "Approved" },
              { value: "rejected", label: "Rejected" },
            ]}
          />
        </div>

        {error && (
          <Notice tone="error" action={<Button size="sm" onClick={load}>Retry</Button>}>
            {error}
          </Notice>
        )}

        <div className={t.wrap}>
          {data === null ? (
            <div aria-busy="true">
              {Array.from({ length: 4 }, (_, i) => (
                <div key={i} className={s.skeletonRow}>
                  <Skeleton width="28%" />
                  <Skeleton width="14%" />
                  <Skeleton width="12%" />
                </div>
              ))}
            </div>
          ) : data.items.length === 0 ? (
            <Empty title={filter === "all" ? "No claims yet" : `No ${filter} claims`}>
              {filter === "all"
                ? "Submitted invoices appear here with their check result and approval status."
                : "Try a different filter."}
            </Empty>
          ) : (
            <div className={t.scroll}>
              <table className={t.table}>
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th className={t.right}>Amount</th>
                    <th>Check</th>
                    <th>Approval</th>
                    <th className={t.hideSm}>Submitted</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((v) => (
                    <tr key={v.id}>
                      <td className={t.truncate}>
                        <span className={t.primaryCell}>
                          {v.invoice?.vendor_name ?? v.file_name ?? "Unknown file"}
                        </span>
                        <span className={`${t.sub} mono`}>
                          {v.extracted_code ? refDisplay(v.extracted_code) : "no reference found"}
                        </span>
                      </td>
                      <td className={t.right}>
                        {v.invoice ? money(v.invoice.amount_cents, v.invoice.currency) : "—"}
                      </td>
                      <td>
                        <ResultStatus result={v.result} />
                      </td>
                      <td>
                        <ApprovalStatus status={v.approval_status} />
                      </td>
                      <td className={`${t.muted} ${t.nowrap} ${t.hideSm}`}>{ago(v.submitted_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </Shell>
  );
}
