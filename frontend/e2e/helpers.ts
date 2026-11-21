import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

// Shared real-backend onboarding path for every e2e spec that needs an
// authenticated Owner with an organization - each call uses its own
// unique email, so specs never collide with each other or with a
// non-empty test database.
export async function registerLoginAndCreateOrg(page: Page): Promise<{ email: string; orgName: string }> {
  const unique = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const email = `e2e-${unique}@flowdesk-e2e.example.com`;
  const orgName = `E2E Org ${unique}`;
  const password = "correct horse battery";

  await page.goto("/register");
  await page.getByLabel("Name").fill("E2E Owner");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "Log in to FlowDesk" })).toBeVisible();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page.getByRole("link", { name: "Create your first organization" })).toBeVisible();
  await page.getByRole("link", { name: "Create your first organization" }).click();

  await expect(page.getByRole("heading", { name: "Create an organization" })).toBeVisible();
  await page.getByLabel("Organization name").fill(orgName);
  await page.getByRole("button", { name: "Create organization" }).click();

  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  return { email, orgName };
}
