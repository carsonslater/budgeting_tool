import { describe, it, expect } from 'vitest';
import { applyScopeError, toApplyScope, DEFAULT_APPLY_CHOICE } from './applyScope';

describe('toApplyScope', () => {
  it('defaults to the server default, until changed', () => {
    expect(toApplyScope(DEFAULT_APPLY_CHOICE)).toEqual({ apply: 'forward' });
  });

  it('sends this month only without a through month', () => {
    expect(toApplyScope({ mode: 'month', through: '2026-12' })).toEqual({ apply: 'month' });
  });

  it('sends the through month only in through mode', () => {
    expect(toApplyScope({ mode: 'through', through: '2026-12' })).toEqual({
      apply: 'through',
      through: '2026-12',
    });
  });
});

describe('applyScopeError', () => {
  it('is never an error outside through mode', () => {
    expect(applyScopeError('2026-10', { mode: 'forward', through: '' })).toBeNull();
    expect(applyScopeError('2026-10', { mode: 'month', through: '2025-01' })).toBeNull();
  });

  it('requires a through month in through mode', () => {
    expect(applyScopeError('2026-10', { mode: 'through', through: '' })).not.toBeNull();
  });

  it('rejects a through month before the selected month', () => {
    expect(applyScopeError('2026-10', { mode: 'through', through: '2026-09' })).not.toBeNull();
  });

  it('accepts the selected month and later months', () => {
    expect(applyScopeError('2026-10', { mode: 'through', through: '2026-10' })).toBeNull();
    expect(applyScopeError('2026-10', { mode: 'through', through: '2027-03' })).toBeNull();
  });
});
