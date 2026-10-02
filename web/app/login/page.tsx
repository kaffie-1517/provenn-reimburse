"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { ThemeToggle } from "@/components/theme";
import { Button, Field, Logo, Notice } from "@/components/ui";
import { api, ApiError, type Session } from "@/lib/api";
import { HOME, useAuth } from "@/lib/auth";
import s from "../auth.module.css";

const DEMO = [
  ["Provider", "provider@demo.com"],
  ["Employee", "employee@acme.com"],
  ["Company admin", "admin@acme.com"],
  ["Platform admin", "padmin@provenn.io"],
] as const;

function safeNext(raw: string | null): string | null {
  // Only same-site paths; never redirect off-site after sign-in.
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : null;
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { ready, user, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace(safeNext(params.get("next")) ?? HOME[user.role]);
  }, [ready, user, params, router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const session = await api<Session>("/api/v1/auth/login", { json: { email, password } });
      signIn(session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't sign in. Try again.");
      setBusy(false);
    }
  }

  return (
    <div className={s.panel}>
      <div className={s.head}>
        <h1>Sign in</h1>
        <p>Use the account your vendor or company set you up with.</p>
      </div>

      <form className={s.form} onSubmit={submit}>
        {error && <Notice tone="error">{error}</Notice>}
        <Field
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button variant="primary" type="submit" loading={busy} className={s.submit}>
          Sign in
        </Button>
      </form>

      <p className={s.alt}>
        New here? <Link href="/register">Create an account</Link>
      </p>

      <div className={s.demo}>
        <p className={s.demoTitle}>Demo accounts · password “password”</p>
        <div className={s.demoList}>
          {DEMO.map(([label, demoEmail]) => (
            <Button
              key={demoEmail}
              size="sm"
              variant="ghost"
              type="button"
              onClick={() => {
                setEmail(demoEmail);
                setPassword("password");
                setError(null);
              }}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className={s.page}>
      <header className={s.top}>
        <Logo />
        <ThemeToggle />
      </header>
      <main className={s.center}>
        <Suspense>
          <LoginForm />
        </Suspense>
      </main>
      <footer className={s.footer}>ProveNN Reimburse</footer>
    </div>
  );
}
