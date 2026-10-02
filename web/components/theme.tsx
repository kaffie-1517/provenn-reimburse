"use client";

import { useSyncExternalStore } from "react";
import s from "./theme.module.css";

type Theme = "system" | "light" | "dark";
const KEY = "provenn.theme";
const ORDER: Theme[] = ["system", "light", "dark"];
const listeners = new Set<() => void>();

function read(): Theme {
  try {
    const t = localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function apply(theme: Theme) {
  try {
    if (theme === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {}
  if (theme === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
  listeners.forEach((l) => l());
}

/** Inline in <head> so the stored theme applies before first paint. */
export const themeBootScript = `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

const LABEL: Record<Theme, string> = { system: "System theme", light: "Light theme", dark: "Dark theme" };

export function ThemeToggle() {
  const theme = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
    () => "system" as Theme,
  );
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];

  return (
    <button
      type="button"
      className={s.toggle}
      onClick={() => apply(next)}
      aria-label={`${LABEL[theme]}. Switch to ${LABEL[next].toLowerCase()}`}
      title={LABEL[theme]}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
        {theme === "light" && (
          <g stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
            <circle cx="8" cy="8" r="3" />
            <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M3.4 12.6l1-1M11.6 4.4l1-1" />
          </g>
        )}
        {theme === "dark" && (
          <path d="M13.5 9.6A5.5 5.5 0 016.4 2.5a5.5 5.5 0 107.1 7.1z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
        )}
        {theme === "system" && (
          <g stroke="currentColor" strokeWidth="1.4">
            <circle cx="8" cy="8" r="5.5" />
            <path d="M8 2.5v11a5.5 5.5 0 000-11z" fill="currentColor" />
          </g>
        )}
      </svg>
    </button>
  );
}
