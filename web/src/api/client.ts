/**
 * api/client.ts — Base fetch helper for all API calls.
 *
 * Base URL is read from VITE_API_URL (set in .env) and defaults to
 * http://localhost:8000 so the dev server talks to the local FastAPI backend.
 */

export const BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  (typeof window !== 'undefined' && window.location.port === '5173'
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : '');

export class ApiError extends Error {
  status: number;
  constructor(
    status: number,
    message: string,
  ) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

/**
 * Typed fetch wrapper. Throws ApiError on non-2xx responses.
 * Returns undefined for 204 No Content.
 */
export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
    ...options,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body?.detail ?? body?.message ?? message;
    } catch {
      // body wasn't JSON — keep the default message
    }
    throw new ApiError(res.status, message);
  }

  return res.json() as Promise<T>;
}

/**
 * Convenience wrappers for common methods.
 */
export const api = {
  get:    <T>(path: string)              => apiFetch<T>(path, { method: 'GET' }),
  post:   <T>(path: string, body: unknown) => apiFetch<T>(path, { method: 'POST',   body: JSON.stringify(body) }),
  patch:  <T>(path: string, body: unknown) => apiFetch<T>(path, { method: 'PATCH',  body: JSON.stringify(body) }),
  delete: <T = void>(path: string)       => apiFetch<T>(path, { method: 'DELETE' }),
} as const;
