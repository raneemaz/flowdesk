import { useEffect, useState } from "react";

// True while the media query matches, kept in sync on resize/rotation.
// Falls back to false where matchMedia doesn't exist (e.g. jsdom), so
// components render their default (desktop) layout there.
export function useMediaQuery(query: string): boolean {
  const get = () => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(query).matches : false);
  const [matches, setMatches] = useState(get);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Below Tailwind's `sm` breakpoint (640px). */
export const PHONE_QUERY = "(max-width: 639px)";
