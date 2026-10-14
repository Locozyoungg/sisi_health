/** Envelope-aware API client. Tokens live in sessionStorage only (staff
 * sessions are short-lived by design — 15-minute idle timeout server-side). */

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
  meta: Record<string, unknown>;
}

const TOKEN_KEY = "sisi_staff_token";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token === null) sessionStorage.removeItem(TOKEN_KEY);
  else sessionStorage.setItem(TOKEN_KEY, token);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const resp = await fetch(path, { ...init, headers });
  const body = (await resp.json()) as Envelope<T>;
  if (!resp.ok || !body.success) {
    throw new Error(body.error?.message ?? `request failed (${resp.status})`);
  }
  return body.data as T;
}
