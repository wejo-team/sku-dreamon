import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

// Browser APIs Vaul's Drawer uses that jsdom does not implement (design-reference/src/test/setup.ts).
beforeEach(() => {
  // Pointer capture is a browser interaction API used by Vaul's drag handling.
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.hasPointerCapture ??= () => false;
  // cmdk scrolls the highlighted result; jsdom has no rendered scroll surface.
  Element.prototype.scrollIntoView ??= () => {};
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  // Vaul observes pointer capabilities; jsdom does not implement media queries.
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => true,
  }));
});

afterEach(cleanup);
