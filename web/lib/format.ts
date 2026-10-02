const moneyCache = new Map<string, Intl.NumberFormat>();

export function money(cents: number, currency = "INR"): string {
  let f = moneyCache.get(currency);
  if (!f) {
    try {
      f = new Intl.NumberFormat("en-IN", { style: "currency", currency });
    } catch {
      f = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    moneyCache.set(currency, f);
  }
  return f.format(cents / 100);
}

const count = new Intl.NumberFormat("en-IN");
export const num = (n: number) => count.format(n);

const day = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const dayTime = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
});

export const date = (iso: string) => day.format(new Date(iso));
export const dateTime = (iso: string) => dayTime.format(new Date(iso));

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
export function ago(iso: string): string {
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(s);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(s / 3600), "hour");
  if (abs < 86400 * 7) return rtf.format(Math.round(s / 86400), "day");
  return date(iso);
}

export const refDisplay = (code: string) => `PNN-${code}`;

/** "PNN-ab cd2345" / "abcd2345" → "ABCD2345", or null. */
export function parseRef(input: string): string | null {
  const code = input.trim().toUpperCase().replace(/\s+/g, "").replace(/^PNN-?/, "");
  return /^[A-Z2-7]{8}$/.test(code) ? code : null;
}

/** "1,500.5" → 150050. String math, so no float rounding surprises. */
export function toCents(input: string): number | null {
  const m = input.replace(/[,\s]/g, "").match(/^(\d{1,9})(?:\.(\d{1,2}))?$/);
  if (!m) return null;
  const cents = Number(m[1]) * 100 + Number((m[2] ?? "").padEnd(2, "0"));
  return cents > 0 ? cents : null;
}

export const shortHash = (h: string) => `${h.slice(0, 10)}…${h.slice(-6)}`;
