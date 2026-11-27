import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "@/App";
// Self-hosted (same origin, cached with the app's own assets) instead of
// the Google Fonts stylesheet, which blocked first paint on a third-party
// request. One variable file covers weights 400-700; the browser only
// fetches the unicode subsets the page actually uses.
import "@fontsource-variable/schibsted-grotesk/wght.css";
import "@/index.css";

// Cloudflare Web Analytics (cookie-free, tracks SPA route changes). Only
// loaded when a site token is configured; the token is public by design.
const analyticsToken = import.meta.env.VITE_CF_ANALYTICS_TOKEN;
if (analyticsToken) {
  const beacon = document.createElement("script");
  beacon.type = "module";
  beacon.src = "https://static.cloudflareinsights.com/beacon.min.js";
  beacon.dataset.cfBeacon = JSON.stringify({ token: analyticsToken });
  document.body.appendChild(beacon);
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element '#root' was not found in index.html.");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
