import "@testing-library/jest-dom/vitest";

// jsdom reports every element's layout box as 0x0 (no real layout
// engine) and has no ResizeObserver at all - Recharts' own
// ResponsiveContainer (features/analytics/charts.tsx, FD-053) reads
// both to size its SVG, and renders nothing inside a 0x0 box, so every
// chart-content assertion in a test would otherwise silently find an
// empty container. This is the standard, widely-used workaround: a
// fixed non-zero box plus a no-op ResizeObserver stub, applied
// globally so individual chart tests don't each need their own.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;

Element.prototype.getBoundingClientRect = () =>
  ({
    width: 600,
    height: 300,
    top: 0,
    left: 0,
    bottom: 300,
    right: 600,
    x: 0,
    y: 0,
    toJSON() {},
  }) as DOMRect;
