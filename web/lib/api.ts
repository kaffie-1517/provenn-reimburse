export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Options = {
  method?: string;
  token?: string | null;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
};

/** FastAPI errors are {detail: string} or {detail: [{msg, loc}]} for validation. */
function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) {
    const first = detail[0] as { msg: string; loc?: unknown[] };
    const field = first.loc?.at(-1);
    return typeof field === "string" ? `${field.replace(/_/g, " ")}: ${first.msg}` : first.msg;
  }
  if (status >= 500) return "Something went wrong on our side. Try again in a moment.";
  return `Request failed (${status})`;
}

async function request(path: string, opts: Options = {}): Promise<Response> {
  const headers: Record<string, string> = {};
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "Can't reach the server. Check your connection.");
  }

  if (!res.ok) {
    const parsed = await res.json().catch(() => null);
    throw new ApiError(res.status, errorMessage(res.status, parsed));
  }
  return res;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const res = await request(path, opts);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** Downloads a binary response and hands it to the browser as a file. */
export async function download(path: string, opts: Options = {}): Promise<{ status: number }> {
  const res = await request(path, opts);
  if (res.status === 202) return { status: 202 };
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "download";
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return { status: res.status };
}

// ── API types ────────────────────────────────────────────────────────────

export type Role = "provider" | "employee" | "company_admin" | "platform_admin";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  company_id: string | null;
  company_name: string | null;
  join_code: string | null;
}

export interface Session {
  token: string;
  user: User;
}

export interface InvoicePublic {
  reference_code: string;
  status: "processing" | "ready";
  ready: boolean;
  vendor_name: string;
  amount_cents: number;
  currency: string;
  invoice_date: string;
  issued_at: string;
}

export interface InvoiceRow extends InvoicePublic {
  id: string;
  purchase_ref: string | null;
  downloaded: boolean;
}

export type Result = "match" | "mismatch" | "not_found";
export type Approval = "pending" | "approved" | "rejected";

export interface Verification {
  id: string;
  result: Result;
  approval_status: Approval;
  extracted_code: string | null;
  submitted_hash: string;
  file_name: string | null;
  submitted_at: string;
  submitter_email: string;
  submitter_name: string;
  approved_at: string | null;
  invoice: {
    reference_code: string;
    vendor_name: string;
    amount_cents: number;
    currency: string;
    invoice_date: string;
  } | null;
}

export interface Page<T> {
  items: T[];
  total: number;
}
