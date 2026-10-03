"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ThemeToggle } from "@/components/theme";
import { Button, Field, Logo, Notice, Segmented } from "@/components/ui";
import { api, ApiError, type Session } from "@/lib/api";
import { HOME, useAuth } from "@/lib/auth";
import s from "../auth.module.css";

type SignupRole = "employee" | "company_admin" | "provider";

const ROLES: { value: SignupRole; label: string; hint: string }[] = [
  {
    value: "employee",
    label: "Employee",
    hint: "Submit invoices for reimbursement. You'll need your company's join code.",
  },
  {
    value: "company_admin",
    label: "Finance",
    hint: "Create a workspace for your company to review claims and invite employees.",
  },
  {
    value: "provider",
    label: "Vendor",
    hint: "Issue tamper-evident invoices to your customers.",
  },
];

export default function RegisterPage() {
  const router = useRouter();
  const { ready, user, signIn } = useAuth();
  const [role, setRole] = useState<SignupRole>("employee");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [company, setCompany] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace(HOME[user.role]);
  }, [ready, user, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const session = await api<Session>("/api/v1/auth/register", {
        json: {
          name,
          email,
          password,
          role,
          company_name: role === "company_admin" ? company : undefined,
          join_code: role === "employee" ? joinCode : undefined,
        },
      });
      signIn(session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the account. Try again.");
      setBusy(false);
    }
  }

  const current = ROLES.find((r) => r.value === role)!;

  return (
    <div className={s.page}>
      <header className={s.top}>
        <Logo />
        <ThemeToggle />
      </header>
      <main className={s.center}>
        <div className={s.panel}>
          <div className={s.head}>
            <h1>Create your account</h1>
            <p>Choose how you&apos;ll use ProveNN.</p>
          </div>

          <form className={s.form} onSubmit={submit}>
            <Segmented
              fill
              label="Account type"
              value={role}
              options={ROLES.map(({ value, label }) => ({ value, label }))}
              onChange={(r) => {
                setRole(r);
                setError(null);
              }}
            />
            <p className={s.roleHint}>{current.hint}</p>

            {error && <Notice tone="error">{error}</Notice>}

            {role === "company_admin" && (
              <Field
                label="Company name"
                required
                minLength={2}
                autoComplete="organization"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
              />
            )}
            {role === "employee" && (
              <Field
                label="Company join code"
                required
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                placeholder="8 characters"
                autoComplete="off"
                spellCheck={false}
                hint="Your finance team can find it in their review queue."
              />
            )}
            <Field
              label={role === "provider" ? "Business name" : "Full name"}
              required
              minLength={2}
              maxLength={120}
              autoComplete={role === "provider" ? "organization" : "name"}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={role === "provider" ? "Air India" : "Rohan Mehta"}
            />
            <Field
              label="Work email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Field
              label="Password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              hint="At least 8 characters."
            />
            <Button variant="primary" type="submit" loading={busy} className={s.submit}>
              Create account
            </Button>
          </form>

          <p className={s.alt}>
            Already have an account? <Link href="/login">Sign in</Link>
          </p>
        </div>
      </main>
      <footer className={s.footer}>ProveNN Reimburse</footer>
    </div>
  );
}
