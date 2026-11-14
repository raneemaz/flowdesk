import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // Makes every API call same-origin from the browser's point of
      // view (see src/api/client.ts for why that matters for the
      // session cookie) instead of requiring CORS-with-credentials on
      // the backend for local dev.
      "/api": {
        target: "http://localhost:5000",
        changeOrigin: true,
      },
    },
  },
});
