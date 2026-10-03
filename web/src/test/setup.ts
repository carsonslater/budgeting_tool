/**
 * Test environment setup.
 *
 * jsdom ships no layout engine, so the two browser APIs recharts reaches for
 * during a render have to be stood in for. Neither needs to do real work —
 * charts render at zero size in tests, which is fine because we assert on
 * table content, not on chart geometry.
 */

import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false;
    },
  }),
});

afterEach(() => {
  cleanup();
});
