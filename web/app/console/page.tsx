"use client";

import { useCallback, useEffect, useState } from "react";
import { Shell, ShellPlaceholder } from "@/components/shell";
import { Button, Empty, Notice, Segmented, Skeleton } from "@/components/ui";
import t from "@/components/table.module.css";
import { api } from "@/lib/api";
import { useRequireRole } from "@/lib/auth";
import { date, money, num } from "@/lib/format";
import s from "./console.module.css";

interface PartnerUsage {
  id: string;
  name: string;
  created_at: string;
  invoices_issued: number;
  downloads: number;
  billed_cents: number;
}

interface CompanyUsage {
  id: string;
  name: string;
  plan: string;
  created_at: string;
  members: number;
  verifications: number;
  matches: number;
  mismatches: number;
  not_found: number;
  approved: number;
}

interface Reports {
  partners: PartnerUsage[];
  direct: { invoices: number; downloads: number; billed_cents: number };
  companies: CompanyUsage[];
}

type Window = "7" | "30" | "90";
type View = "partners" | "companies";

const pct = (part: number, whole: number) => (whole ? `${Math.round((100 * part) / whole)}%` : "—");

export default function ConsolePage() {
  const session = useRequireRole("platform_admin");
  const token = session?.token;
  const [days, setDays] = useState<Window>("30");
  const [view, setView] = useState<View>("partners");
  const [data, setData] = useState<Reports | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const [p, c] = await Promise.all([
        api<{ partners: PartnerUsage[]; direct: Reports["direct"] }>(`/api/v1/admin/partners?days=${days}`, { token }),
        api<{ companies: CompanyUsage[] }>(`/api/v1/admin/companies?days=${days}`, { token }),
      ]);
      setData({ partners: p.partners, direct: p.direct, companies: c.companies });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load reports");
    }
  }, [token, days]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on window change
    setData(null);
    load();
  }, [load]);

  if (!session) return <ShellPlaceholder />;

  const sum = <T,>(rows: T[] | undefined, f: (r: T) => number) => (rows ?? []).reduce((n, r) => n + f(r), 0);
  const issued = sum(data?.partners, (p) => p.invoices_issued) + (data?.direct.invoices ?? 0);
  const billed = sum(data?.partners, (p) => p.billed_cents) + (data?.direct.billed_cents ?? 0);
  const checks = sum(data?.companies, (c) => c.verifications);
  const mismatches = sum(data?.companies, (c) => c.mismatches);

  const kpis = [
    { label: "Invoices issued", value: num(issued) },
    { label: "Billed", value: money(billed) },
    { label: "Claims checked", value: num(checks) },
    {
      label: "Mismatches caught",
      value: num(mismatches),
      note: checks ? `${pct(mismatches, checks)} of claims` : undefined,
      bad: mismatches > 0,
    },
  ];

  return (
    <Shell
      title="Console"
      description="Usage across every partner and company on the platform."
      actions={
        <Segmented
          label="Time window"
          value={days}
          onChange={setDays}
          options={[
            { value: "7", label: "7 days" },
            { value: "30", label: "30 days" },
            { value: "90", label: "90 days" },
          ]}
        />
      }
    >
      {error && (
        <Notice tone="error" action={<Button size="sm" onClick={load}>Retry</Button>}>
          {error}
        </Notice>
      )}

      <dl className={s.kpis} aria-busy={!data || undefined}>
        {kpis.map((k) => (
          <div key={k.label} className={s.kpi}>
            <dt>{k.label}</dt>
            <dd className={s.kpiValue}>{data ? k.value : <Skeleton width="60%" />}</dd>
            {data && k.note && <dd className={k.bad ? s.kpiNoteBad : s.kpiNote}>{k.note}</dd>}
          </div>
        ))}
      </dl>

      <div className={s.tableHead}>
        <Segmented
          label="Report"
          value={view}
          onChange={setView}
          options={[
            { value: "partners", label: "Issuers", count: data ? data.partners.length + 1 : undefined },
            { value: "companies", label: "Companies", count: data?.companies.length },
          ]}
        />
      </div>

      <div className={t.wrap}>
        {!data ? (
          <div aria-busy="true">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className={s.skeletonRow}>
                <Skeleton width="24%" />
                <Skeleton width="10%" />
                <Skeleton width="10%" />
              </div>
            ))}
          </div>
        ) : view === "partners" ? (
          <div className={t.scroll}>
            <table className={t.table}>
              <thead>
                <tr>
                  <th>Issuer</th>
                  <th className={t.right}>Invoices</th>
                  <th className={t.right}>Downloads</th>
                  <th className={t.right}>Billed</th>
                  <th className={t.hideSm}>Since</th>
                </tr>
              </thead>
              <tbody>
                {data.partners.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <span className={t.primaryCell}>{p.name}</span>
                      <span className={t.sub}>API partner</span>
                    </td>
                    <td className={t.right}>{num(p.invoices_issued)}</td>
                    <td className={t.right}>{num(p.downloads)}</td>
                    <td className={t.right}>{money(p.billed_cents)}</td>
                    <td className={`${t.muted} ${t.hideSm}`}>{date(p.created_at)}</td>
                  </tr>
                ))}
                <tr className={s.directRow}>
                  <td>
                    <span className={t.primaryCell}>Vendor portal</span>
                    <span className={t.sub}>Invoices issued by provider accounts</span>
                  </td>
                  <td className={t.right}>{num(data.direct.invoices)}</td>
                  <td className={t.right}>{num(data.direct.downloads)}</td>
                  <td className={t.right}>{money(data.direct.billed_cents)}</td>
                  <td className={t.hideSm} />
                </tr>
              </tbody>
            </table>
          </div>
        ) : data.companies.length === 0 ? (
          <Empty title="No companies yet">Companies appear here once a finance admin signs up.</Empty>
        ) : (
          <div className={t.scroll}>
            <table className={t.table}>
              <thead>
                <tr>
                  <th>Company</th>
                  <th className={t.hideSm}>Plan</th>
                  <th className={t.right}>Members</th>
                  <th className={t.right}>Claims</th>
                  <th className={t.right}>Mismatch</th>
                  <th className={t.right}>Approved</th>
                </tr>
              </thead>
              <tbody>
                {data.companies.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className={t.primaryCell}>{c.name}</span>
                      <span className={t.sub}>since {date(c.created_at)}</span>
                    </td>
                    <td className={`${t.muted} ${t.hideSm} ${s.plan}`}>{c.plan}</td>
                    <td className={t.right}>{num(c.members)}</td>
                    <td className={t.right}>{num(c.verifications)}</td>
                    <td className={t.right}>
                      {c.mismatches ? (
                        <span className={s.bad}>
                          {num(c.mismatches)} <span className={s.rate}>({pct(c.mismatches, c.verifications)})</span>
                        </span>
                      ) : (
                        <span className={t.muted}>0</span>
                      )}
                    </td>
                    <td className={t.right}>{num(c.approved)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Shell>
  );
}
