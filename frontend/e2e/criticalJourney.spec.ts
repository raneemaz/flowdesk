import { expect, test } from "@playwright/test";

import { registerLoginAndCreateOrg } from "./helpers";

// FD-063: the one real-browser, real-backend critical journey -
// register, log in, create the first organization, land on a fully
// wired dashboard - complementing src/integration/newOrganizationJourney.test.tsx's
// mocked version of the same journey.
test("a brand-new user registers, logs in, and creates their first organization", async ({ page }) => {
  await registerLoginAndCreateOrg(page);

  // Back on "/", now as the new org's Owner - the full Sidebar, not
  // the "no organization" prompt.
  await expect(page.getByText("You don't belong to an organization yet.")).not.toBeVisible();
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav.getByRole("link", { name: "Invoices" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Departments" })).toBeVisible();
});
