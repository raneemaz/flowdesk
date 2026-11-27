import { cn } from "@/lib/utils";

// The FlowDesk mark: an "F" whose stem curves into the top bar - work
// flowing through one place - with the gold middle bar. On dark
// surfaces (the sidebar) the tile flips to paper so the mark keeps its
// contrast. Same drawing as public/favicon.svg.
interface LogoProps {
  /** "light" for paper backgrounds, "dark" for the green sidebar/bands. */
  tone?: "light" | "dark";
  /** Hide the "FlowDesk" wordmark (e.g. collapsed sidebar). */
  markOnly?: boolean;
  className?: string;
  /** Mark size in px. */
  size?: number;
}

export function LogoMark({ tone = "light", size = 32, className }: Omit<LogoProps, "markOnly">) {
  const tile = tone === "light" ? "#163A2D" : "#F1F3EE";
  const stroke = tone === "light" ? "#F1F3EE" : "#163A2D";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className={cn("flex-shrink-0", className)}>
      <rect width="32" height="32" rx="8" fill={tile} />
      <path d="M10.5 24V13.5a5.5 5.5 0 0 1 5.5-5.5h7" fill="none" stroke={stroke} strokeWidth="3.6" strokeLinecap="round" />
      <path d="M10.5 17h8" fill="none" stroke="#D6A43A" strokeWidth="3.6" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ tone = "light", markOnly = false, className, size = 32 }: LogoProps) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark tone={tone} size={size} />
      {!markOnly && (
        <span
          className={cn(
            "text-[1.35rem] font-bold leading-none tracking-[-0.03em]",
            tone === "light" ? "text-foreground" : "text-sidebar-foreground",
          )}
        >
          FlowDesk
        </span>
      )}
      {markOnly && <span className="sr-only">FlowDesk</span>}
    </span>
  );
}
