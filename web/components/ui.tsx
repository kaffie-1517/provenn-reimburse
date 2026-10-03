"use client";

import Link from "next/link";
import {
  useEffect,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import type { Approval, Result } from "@/lib/api";
import s from "./ui.module.css";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// ── Button ─────────────────────────────────────────────────────────────────

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
  loading?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cx(s.btn, s[variant], size === "sm" && s.sm, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className={s.spinner} aria-hidden />}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  children,
}: {
  href: string;
  variant?: Variant;
  size?: "sm" | "md";
  children: ReactNode;
}) {
  return (
    <Link href={href} className={cx(s.btn, s[variant], size === "sm" && s.sm)}>
      {children}
    </Link>
  );
}

// ── Field ──────────────────────────────────────────────────────────────────

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
  prefix?: string;
}

export function Field({ label, hint, error, optional, prefix, className, ...input }: FieldProps) {
  const id = useId();
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined;
  const control = (
    <input
      id={id}
      className={s.input}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy}
      {...input}
    />
  );
  return (
    <div className={cx(s.field, className)}>
      <label htmlFor={id} className={s.label}>
        {label} {optional && <span className={s.optional}>(optional)</span>}
      </label>
      {prefix ? (
        <div className={s.affix}>
          <span className={s.prefix} aria-hidden>
            {prefix}
          </span>
          {control}
        </div>
      ) : (
        control
      )}
      {error ? (
        <span id={`${id}-err`} className={s.fieldError} role="alert">
          {error}
        </span>
      ) : (
        hint && (
          <span id={`${id}-hint`} className={s.hint}>
            {hint}
          </span>
        )
      )}
    </div>
  );
}

// ── Status ─────────────────────────────────────────────────────────────────

type Tone = "ok" | "bad" | "warn" | "muted";

export function Status({ tone, pulse, children }: { tone: Tone; pulse?: boolean; children: ReactNode }) {
  return <span className={cx(s.status, s[`tone-${tone}`], pulse && s.pulse)}>{children}</span>;
}

const RESULT: Record<Result, [Tone, string]> = {
  match: ["ok", "Match"],
  mismatch: ["bad", "Mismatch"],
  not_found: ["muted", "Not issued"],
};

const APPROVAL: Record<Approval, [Tone, string]> = {
  pending: ["warn", "Pending"],
  approved: ["ok", "Approved"],
  rejected: ["muted", "Rejected"],
};

export const ResultStatus = ({ result }: { result: Result }) => (
  <Status tone={RESULT[result][0]}>{RESULT[result][1]}</Status>
);

export const ApprovalStatus = ({ status }: { status: Approval }) => (
  <Status tone={APPROVAL[status][0]}>{APPROVAL[status][1]}</Status>
);

// ── Notice ─────────────────────────────────────────────────────────────────

export function Notice({
  tone = "info",
  children,
  action,
}: {
  tone?: "info" | "error" | "success";
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={cx(s.notice, s[`notice-${tone}`])} role={tone === "error" ? "alert" : "status"}>
      <div className={s.noticeBody}>{children}</div>
      {action}
    </div>
  );
}

// ── Empty ──────────────────────────────────────────────────────────────────

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={s.empty}>
      <p className={s.emptyTitle}>{title}</p>
      {children && <p className={s.emptyBody}>{children}</p>}
      {action && <div className={s.emptyAction}>{action}</div>}
    </div>
  );
}

// ── Skeleton ───────────────────────────────────────────────────────────────

export const Skeleton = ({ width = "100%" }: { width?: string | number }) => (
  <span className={s.skeleton} style={{ width }} aria-hidden />
);

// ── Segmented ──────────────────────────────────────────────────────────────

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  fill,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (v: T) => void;
  /** Stretch to the container with equal-width segments. */
  fill?: boolean;
}) {
  return (
    <div className={cx(s.segmented, fill && s.fill)} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={s.segment}
          onClick={() => onChange(o.value)}
        >
          {o.label}
          {o.count !== undefined && <span className={s.segmentCount}>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ── Copy ───────────────────────────────────────────────────────────────────

export function Copy({ text, children }: { text: string; children?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1400);
    return () => clearTimeout(t);
  }, [copied]);
  return (
    <button
      type="button"
      className={s.copy}
      onClick={() => navigator.clipboard?.writeText(text).then(() => setCopied(true))}
      title="Copy"
    >
      {children ?? text}
      <span className={s.copyHint} aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </button>
  );
}

// ── Logo ───────────────────────────────────────────────────────────────────

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className={s.logo} aria-label="ProveNN home">
      <svg className={s.logoMark} width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden>
        <rect x="1.5" y="1.5" width="17" height="17" rx="4" stroke="currentColor" strokeWidth="1.6" />
        <path d="M6 10.4l2.6 2.6L14 7.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      ProveNN
    </Link>
  );
}
