import { apiFetch, BASE_URL } from './client';
import type { StagedRow, ImportResult } from '../types';

/**
 * Upload a CSV file. Returns staged (unpersisted) rows with duplicate flags
 * and auto-categorization applied by the backend.
 */
export const stageImport = async (file: File): Promise<StagedRow[]> => {
  const form = new FormData();
  form.append('file', file);

  // Use apiFetch directly so we can set multipart body without Content-Type override
  const res = await fetch(`${BASE_URL}/api/import`, {
    method: 'POST',
    body: form,
    // Do NOT set Content-Type — browser sets it with the correct boundary
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body?.detail ?? message;
    } catch { /* ignore */ }
    throw new Error(message);
  }

  return res.json() as Promise<StagedRow[]>;
};

/**
 * Persist selected staged rows. Backend re-checks for duplicates.
 */
export const confirmImport = (rows: StagedRow[]): Promise<ImportResult> =>
  apiFetch<ImportResult>('/api/import/confirm', {
    method: 'POST',
    body: JSON.stringify({ rows }),
  });
