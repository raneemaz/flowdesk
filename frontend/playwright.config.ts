import path from "node:path";
import { defineConfig } from "@playwright/test";

// FD-063: real-browser critical-journey and responsiveness tests,
// against the real backend (FLASK_ENV=testing - a real Postgres test
// database, same convention backend/tests/ already requires) and the
// real Vite dev server - never a mocked API layer, unlike
// src/integration/*.test.tsx. `channel: "chrome"` uses the machine's
// own installed Chrome rather than Playwright's bundled Chromium -
// this repo deliberately doesn't vendor a browser download.
//
// Every spec creates its own unique user/organization per run (same
// "unique email, no shared fixture state" convention
// backend/tests/integration/ already established) rather than relying
// on a clean/seeded database, so re-running against a non-empty test
// database is always safe.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    channel: "chrome",
    baseURL: "http://localhost:5173",
  },
  webServer: [
    {
      command: "npm run dev -- --port 5173",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "FLASK_ENV=testing ./.venv/Scripts/python.exe -m flask --app wsgi run",
      cwd: path.resolve(import.meta.dirname, "../backend"),
      url: "http://localhost:5000/api/v1/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
