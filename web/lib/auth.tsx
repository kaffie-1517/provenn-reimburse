"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, type Role, type Session, type User } from "./api";

const KEY = "provenn.session";

interface AuthValue {
  /** false until the stored session has been read; render nothing auth-dependent before. */
  ready: boolean;
  token: string | null;
  user: User | null;
  signIn: (s: Session) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

function readStored(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = readStored();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate from storage once
    setSession(stored);
    setReady(true);
    if (!stored) return;
    // Refresh the profile (and drop a session the server no longer accepts).
    api<User>("/api/v1/auth/me", { token: stored.token })
      .then((user) => {
        const next = { token: stored.token, user };
        setSession(next);
        localStorage.setItem(KEY, JSON.stringify(next));
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          localStorage.removeItem(KEY);
          setSession(null);
        }
      });
  }, []);

  const signIn = useCallback((s: Session) => {
    localStorage.setItem(KEY, JSON.stringify(s));
    setSession(s);
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(KEY);
    setSession(null);
  }, []);

  const value = useMemo(
    () => ({ ready, token: session?.token ?? null, user: session?.user ?? null, signIn, signOut }),
    [ready, session, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export const HOME: Record<Role, string> = {
  provider: "/provider",
  employee: "/claims",
  company_admin: "/review",
  platform_admin: "/console",
};

export const ROLE_LABEL: Record<Role, string> = {
  provider: "Provider",
  employee: "Employee",
  company_admin: "Company admin",
  platform_admin: "Platform admin",
};

/**
 * Gate for a page that needs one specific role. Signed-out visitors go to
 * /login (and come back afterwards); other roles go to their own home.
 * Returns the session only once the check has passed.
 */
export function useRequireRole(role: Role): { token: string; user: User } | null {
  const { ready, token, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    if (!token || !user) {
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    } else if (user.role !== role) {
      router.replace(HOME[user.role]);
    }
  }, [ready, token, user, role, router]);

  return ready && token && user && user.role === role ? { token, user } : null;
}
