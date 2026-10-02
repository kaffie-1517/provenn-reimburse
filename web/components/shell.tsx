"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ROLE_LABEL, useAuth } from "@/lib/auth";
import { ThemeToggle } from "./theme";
import { Logo } from "./ui";
import s from "./shell.module.css";

function AccountMenu() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;
  const initial = user.email[0]?.toUpperCase();

  return (
    <div className={s.account} ref={ref}>
      <button
        className={s.accountButton}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={s.avatar} aria-hidden>
          {initial}
        </span>
        <span className={s.accountEmail}>{user.email}</span>
      </button>
      {open && (
        <div className={s.menu} role="menu">
          <div className={s.menuHeader}>
            <span className={s.menuEmail}>{user.email}</span>
            <span className={s.menuRole}>
              {ROLE_LABEL[user.role]}
              {user.company_name ? ` · ${user.company_name}` : ""}
            </span>
          </div>
          <button
            role="menuitem"
            className={s.menuItem}
            onClick={() => {
              signOut();
              router.replace("/login");
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/** Frame for signed-in workspaces: top bar + page header + content. */
export function Shell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const { user } = useAuth();
  return (
    <div className={s.frame}>
      <header className={s.bar}>
        <div className={s.barInner}>
          <div className={s.barLeft}>
            <Logo href="/" />
            {user && (
              <span className={s.context}>
                <span className={s.slash} aria-hidden>
                  /
                </span>
                {user.company_name ?? ROLE_LABEL[user.role]}
              </span>
            )}
          </div>
          <div className={s.barRight}>
            <ThemeToggle />
            <AccountMenu />
          </div>
        </div>
      </header>
      <main className={s.main}>
        <div className={s.pageHead}>
          <div className={s.titles}>
            <h1 className={s.title}>{title}</h1>
            {description && <p className={s.description}>{description}</p>}
          </div>
          {actions && <div className={s.actions}>{actions}</div>}
        </div>
        {children}
      </main>
    </div>
  );
}

/** Blank frame used while a role gate is resolving, so the layout doesn't jump. */
export function ShellPlaceholder() {
  return <div className={s.frame} aria-busy="true" />;
}
