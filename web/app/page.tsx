"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ThemeToggle } from "@/components/theme";
import { Button, ButtonLink, Logo } from "@/components/ui";
import { HOME, useAuth } from "@/lib/auth";
import { parseRef } from "@/lib/format";
import s from "./landing.module.css";

const STEPS = [
  {
    title: "Issue",
    body: "The vendor uploads the invoice, or their billing system sends it over the API. ProveNN stamps a reference code and QR on every page and records the file's SHA-256.",
  },
  {
    title: "Share",
    body: "The buyer downloads the stamped PDF. That exact file — byte for byte — is the only copy that will verify later.",
  },
  {
    title: "Verify",
    body: "When an employee submits it for reimbursement, the file is hashed again. If anything changed, finance sees a mismatch before approving.",
  },
];

const AUDIENCE = [
  ["Vendors", "Issue invoices from the portal or your billing system via API key."],
  ["Employees", "Upload the invoice you received; know immediately if it checks out."],
  ["Finance teams", "Review a queue of verified claims, approve, and export to your ERP."],
];

function Lookup() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const code = parseRef(value);
    if (!code) {
      setError("Reference codes are 8 characters, like PNN-7Q4MZK2D.");
      return;
    }
    router.push(`/i/${code}`);
  }

  return (
    <form className={s.lookup} onSubmit={submit} noValidate>
      <label htmlFor="ref" className={s.lookupLabel}>
        Have an invoice from a ProveNN vendor?
      </label>
      <div className={s.lookupRow}>
        <div className={s.lookupInput}>
          <span className={s.lookupPrefix} aria-hidden>
            PNN-
          </span>
          <input
            id="ref"
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setError(null);
            }}
            placeholder="7Q4MZK2D"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "ref-error" : undefined}
          />
        </div>
        <Button variant="primary" type="submit">
          Look up
        </Button>
      </div>
      {error && (
        <p id="ref-error" className={s.lookupError} role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

function Specimen() {
  return (
    <figure className={s.specimen} aria-label="Example: how verification compares files">
      <div className={s.specHead}>
        <span className="mono">PNN-7Q4MZK2D</span>
        <span className={s.specMeta}>Northwind Traders · ₹42,000.00</span>
      </div>
      <dl className={s.specRows}>
        <div className={s.specRow}>
          <dt>Issued</dt>
          <dd className="mono">9f2c 41e0 77ab … a41e</dd>
          <dd className={s.specNote}>fingerprint on record</dd>
        </div>
        <div className={s.specRow}>
          <dt>Submitted copy</dt>
          <dd className="mono">9f2c 41e0 77ab … a41e</dd>
          <dd className={s.specOk}>Match</dd>
        </div>
        <div className={s.specRow}>
          <dt>
            Edited copy
            <span className={s.specSub}>₹42,000 → ₹92,000</span>
          </dt>
          <dd className="mono">
            <span className={s.diff}>41b7 0e5d c2f9</span> … 0c9d
          </dd>
          <dd className={s.specBad}>Mismatch</dd>
        </div>
      </dl>
      <figcaption className={s.specCaption}>
        One changed character produces a completely different fingerprint.
      </figcaption>
    </figure>
  );
}

export default function Landing() {
  const { ready, user } = useAuth();

  return (
    <div className={s.page}>
      <header className={s.nav}>
        <Logo />
        <nav className={s.navRight} aria-label="Account">
          <ThemeToggle />
          {ready &&
            (user ? (
              <ButtonLink href={HOME[user.role]} variant="primary" size="sm">
                Open workspace
              </ButtonLink>
            ) : (
              <>
                <Link href="/login" className={s.navLink}>
                  Sign in
                </Link>
                <ButtonLink href="/register" variant="primary" size="sm">
                  Get started
                </ButtonLink>
              </>
            ))}
        </nav>
      </header>

      <main>
        <section className={s.hero}>
          <div className={s.heroCopy}>
            <p className={s.eyebrow}>Expense integrity</p>
            <h1 className={s.headline}>Reimburse the invoice that was actually issued.</h1>
            <p className={s.lede}>
              ProveNN fingerprints every invoice at the source and checks it again at expense
              time. Edited amounts, swapped vendors and re-generated PDFs are flagged before
              anyone approves them.
            </p>
            <Lookup />
          </div>
          <Specimen />
        </section>

        <section className={s.section} aria-labelledby="how">
          <h2 id="how" className={s.sectionTitle}>
            How it works
          </h2>
          <ol className={s.steps}>
            {STEPS.map((step, i) => (
              <li key={step.title} className={s.step}>
                <span className={s.stepNo}>{String(i + 1).padStart(2, "0")}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className={s.section} aria-labelledby="who">
          <h2 id="who" className={s.sectionTitle}>
            Who uses it
          </h2>
          <dl className={s.audience}>
            {AUDIENCE.map(([who, what]) => (
              <div key={who} className={s.audienceRow}>
                <dt>{who}</dt>
                <dd>{what}</dd>
              </div>
            ))}
          </dl>
        </section>
      </main>

      <footer className={s.footer}>
        <span>ProveNN Reimburse</span>
        <span>SHA-256 fingerprints · reference codes · audit-ready exports</span>
      </footer>
    </div>
  );
}
