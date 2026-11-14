// A short, curated list rather than Intl.supportedValuesOf (inconsistent
// browser support, and non-deterministic in tests) - the backend accepts
// any 3-letter ISO 4217 / any IANA zone string regardless, so this is purely
// a convenience shortlist for the creation form, not a validation source.
export const COMMON_CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR"] as const;

export const COMMON_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
] as const;
