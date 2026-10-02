"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useState } from "react";
import { Shell, ShellPlaceholder } from "@/components/shell";
import {
  ApprovalStatus,
  Button,
  Copy,
  Empty,
  Notice,
  ResultStatus,
  Segmented,
  Skeleton,
} from "@/components/ui";
import t from "@/components/table.module.css";
import { api, ApiError, download, type Approval, type Page, type Verification } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { ago, dateTime, money, refDisplay } from "@/lib/format";
import s from "./review.module.css";

type Tab = Approval | "all";
type ResultFilter = "" | "match" | "mismatch" | "not_found";
const PAGE = 50;

function Decide({
  v,
  token,
  onDecided,
}: {
  v: Verification;
  token: string;
  onDecided: (updated: Verification) => void;
}) {
  const [busy, setBusy] = useState<"approved" | "rejected" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const risky = v.result !== "match";

  async function decide(decision: "approved" | "rejected") {
    if (decision === "approved" && risky && !confirming) {
      setConfirming(true);
      return;
    }
    setBusy(decision);
    setError(null);
    try {
      onDecided(
        await api<Verification>(`/api/v1/verifications/${v.id}`, {
          method: "PATCH",
          token,
          json: { decision },
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed");
      setBusy(null);
      setConfirming(false);
    }
  }

  return (
    <div className={s.decide}>
      {error && <span className={s.decideError}>{error}</span>}
      <Button
        size="sm"
        variant="danger"
        onClick={() => decide("rejected")}
        loading={busy === "rejected"}
        disabled={busy !== null}
      >
        Reject
      </Button>
      <Button
        size="sm"
        variant={risky && !confirming ? "secondary" : "primary"}
        onClick={() => decide("approved")}
        onBlur={() => setConfirming(false)}
        loading={busy === "approved"}
        disabled={busy !== null}
      >
        {confirming ? "Confirm approval" : risky ? "Approve anyway" : "Approve"}
      </Button>
    </div>
  );
}

function Details({ v }: { v: Verification }) {
  return (
    <dl className={s.details}>
      <div>
        <dt>File</dt>
        <dd>{v.file_name ?? "—"}</dd>
      </div>
      <div>
        <dt>Submitted</dt>
        <dd>{dateTime(v.submitted_at)}</dd>
      </div>
      <div>
        <dt>Submitted fingerprint (SHA-256)</dt>
        <dd className={`mono ${s.hash}`}>{v.submitted_hash}</dd>
      </div>
      {v.invoice && (
        <div>
          <dt>Issued invoice</dt>
          <dd>
            <Link href={`/i/${v.invoice.reference_code}`}>Open {refDisplay(v.invoice.reference_code)}</Link>
          </dd>
        </div>
      )}
      {v.approved_at && (
        <div>
          <dt>Decided</dt>
          <dd>{dateTime(v.approved_at)}</dd>
        </div>
      )}
    </dl>
  );
}

export default function ReviewPage() {
  const session = useRequireRole("company_admin");
  const token = session?.token;
  const [tab, setTab] = useState<Tab>("pending");
  const [resultFilter, setResultFilter] = useState<ResultFilter>("");
  const [data, setData] = useState<Page<Verification> | null>(null);
  const [counts, setCounts] = useState<Record<Approval, number> | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const query = useCallback(
    (offset: number) => {
      const p = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
      if (tab !== "all") p.set("approval_status", tab);
      if (resultFilter) p.set("result", resultFilter);
      return `/api/v1/verifications?${p}`;
    },
    [tab, resultFilter],
  );

  const loadCounts = useCallback(async () => {
    if (!token) return;
    const totals = await Promise.all(
      (["pending", "approved", "rejected"] as const).map((st) =>
        api<Page<Verification>>(`/api/v1/verifications?limit=1&approval_status=${st}`, { token }).then(
          (r) => [st, r.total] as const,
        ),
      ),
    );
    setCounts(Object.fromEntries(totals) as Record<Approval, number>);
  }, [token]);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setData(await api<Page<Verification>>(query(0), { token }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load claims");
    }
  }, [token, query]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on filter change
    setData(null);
    load();
  }, [load]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch
    loadCounts().catch(() => {});
  }, [loadCounts]);

  async function more() {
    if (!token || !data) return;
    setLoadingMore(true);
    try {
      const next = await api<Page<Verification>>(query(data.items.length), { token });
      setData({ total: next.total, items: [...data.items, ...next.items] });
    } finally {
      setLoadingMore(false);
    }
  }

  function onDecided(updated: Verification) {
    setData((d) => {
      if (!d) return d;
      // In a status tab the row no longer belongs; in "all" it updates in place.
      if (tab !== "all" && tab !== updated.approval_status) {
        return { total: d.total - 1, items: d.items.filter((x) => x.id !== updated.id) };
      }
      return { ...d, items: d.items.map((x) => (x.id === updated.id ? updated : x)) };
    });
    loadCounts().catch(() => {});
  }

  async function exportXlsx() {
    if (!token) return;
    setExporting(true);
    setExportError(null);
    try {
      await download("/api/v1/verifications/export", { token });
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  if (!session) return <ShellPlaceholder />;
  const joinCode = session.user.join_code;

  return (
    <Shell
      title="Review"
      description="Every claim is checked against the invoice as issued. Approve what matches; investigate the rest."
      actions={
        <>
          {joinCode && (
            <span className={s.join}>
              <span className={s.joinLabel}>Employee join code</span>
              <Copy text={joinCode} />
            </span>
          )}
          <Button onClick={exportXlsx} loading={exporting}>
            Export approved
          </Button>
        </>
      }
    >
      {exportError && <Notice tone="error">{exportError}</Notice>}

      <div className={s.toolbar}>
        <Segmented
          label="Approval status"
          value={tab}
          onChange={(v) => {
            setTab(v);
            setOpen(null);
          }}
          options={[
            { value: "pending", label: "Pending", count: counts?.pending },
            { value: "approved", label: "Approved", count: counts?.approved },
            { value: "rejected", label: "Rejected", count: counts?.rejected },
            { value: "all", label: "All" },
          ]}
        />
        <label className={s.filter}>
          <span className="sr-only">Check result</span>
          <select value={resultFilter} onChange={(e) => setResultFilter(e.target.value as ResultFilter)}>
            <option value="">Any check result</option>
            <option value="match">Match</option>
            <option value="mismatch">Mismatch</option>
            <option value="not_found">Not issued</option>
          </select>
        </label>
      </div>

      {error && (
        <Notice tone="error" action={<Button size="sm" onClick={load}>Retry</Button>}>
          {error}
        </Notice>
      )}

      <div className={t.wrap}>
        {data === null ? (
          <div aria-busy="true">
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className={s.skeletonRow}>
                <Skeleton width="20%" />
                <Skeleton width="26%" />
                <Skeleton width="12%" />
                <Skeleton width="10%" />
              </div>
            ))}
          </div>
        ) : data.items.length === 0 ? (
          <Empty
            title={tab === "pending" ? "Nothing waiting for review" : "No claims here"}
            action={
              joinCode && tab === "pending" ? (
                <span className={s.emptyJoin}>
                  Employees join with code <Copy text={joinCode} />
                </span>
              ) : undefined
            }
          >
            {tab === "pending"
              ? "New claims land here as soon as employees submit them."
              : "Try a different status or check result."}
          </Empty>
        ) : (
          <>
            <div className={t.scroll}>
              <table className={t.table}>
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>Invoice</th>
                    <th className={t.right}>Amount</th>
                    <th>Check</th>
                    <th className={t.hideSm}>Submitted</th>
                    <th className={t.right}>{tab === "pending" ? "Decision" : "Status"}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((v) => {
                    const expanded = open === v.id;
                    return (
                      <Fragment key={v.id}>
                        <tr className={s.row} data-expanded={expanded || undefined}>
                          <td className={t.truncate}>
                            <button
                              className={s.expand}
                              aria-expanded={expanded}
                              aria-label={`Details for ${v.submitter_email}'s claim`}
                              onClick={() => setOpen(expanded ? null : v.id)}
                            >
                              <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
                                <path d="M3 2l3 3-3 3" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
                              </svg>
                            </button>
                            {v.submitter_email}
                          </td>
                          <td className={t.truncate}>
                            <span className={t.primaryCell}>{v.invoice?.vendor_name ?? "Unknown vendor"}</span>
                            <span className={`${t.sub} mono`}>
                              {v.extracted_code ? refDisplay(v.extracted_code) : "no reference"}
                            </span>
                          </td>
                          <td className={t.right}>
                            {v.invoice ? money(v.invoice.amount_cents, v.invoice.currency) : "—"}
                          </td>
                          <td>
                            <ResultStatus result={v.result} />
                          </td>
                          <td className={`${t.muted} ${t.nowrap} ${t.hideSm}`}>{ago(v.submitted_at)}</td>
                          <td className={t.right}>
                            {v.approval_status === "pending" ? (
                              <Decide v={v} token={session.token} onDecided={onDecided} />
                            ) : (
                              <ApprovalStatus status={v.approval_status} />
                            )}
                          </td>
                        </tr>
                        {expanded && (
                          <tr className={s.detailRow}>
                            <td colSpan={6}>
                              <Details v={v} />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className={t.footer}>
              <span>
                Showing {data.items.length} of {data.total}
              </span>
              {data.items.length < data.total && (
                <Button size="sm" variant="ghost" onClick={more} loading={loadingMore}>
                  Load more
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </Shell>
  );
}
