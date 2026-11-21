import { expect, test } from "@playwright/test";

import { registerLoginAndCreateOrg } from "./helpers";

// FD-063 (NFR-011: "the application is responsive across viewport
// sizes"). The real-browser layer is the only one that can actually
// check this - jsdom (src/integration/*.test.tsx, and every other
// Vitest/RTL test in this codebase) has no real layout engine, so a
// CSS media query or a flex box actually overflowing is invisible to
// it.
test.describe("responsive layout", () => {
  test("the dashboard has no horizontal overflow on a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await registerLoginAndCreateOrg(page);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });

  test("the dashboard has no horizontal overflow on a tablet viewport", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await registerLoginAndCreateOrg(page);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
});
