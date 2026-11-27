import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Play } from "lucide-react";

import { Logo } from "@/components/Logo";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

// The public front door: what FlowDesk is, real screens, the demo video,
// and the way in (log in / create a workspace). Every screen shown is
// the real app running a fictional demo company, Northbeam Digital -
// the footer says so. Nothing here (no customers, quotes or prices) is
// invented.

const TOUR = [
  { id: "overview", label: "Overview", image: "overview", caption: "Tasks, invoices and recent activity on one screen." },
  { id: "tasks", label: "Tasks", image: "board", caption: "Plan on a board, a list or a calendar. Assign and move work forward." },
  { id: "requests", label: "Requests", image: "requests", caption: "Every customer request, with priority, owner and status." },
  { id: "invoices", label: "Invoices", image: "invoice", caption: "Line items, totals and payment status for every invoice." },
  { id: "analytics", label: "Analytics", image: "analytics", caption: "Numbers computed live from your own data." },
  { id: "team", label: "Team", image: "members", caption: "Invite people, give them a role, change it any time." },
] as const;

const FEATURES = [
  {
    title: "Plan the work",
    body: "Board, list, calendar and My Tasks views of the same tasks. Click a day to add a task, assign it, and move it from To Do to Completed.",
    points: ["Comments and a full history on every task", "Overdue work flagged automatically", "Cancel or delete when plans change"],
    image: "calendar",
    focus: { x: 64, y: 58, zoom: 1.35 },
    alt: "The FlowDesk task calendar for a month, with tasks on their due dates",
  },
  {
    title: "Look after customers",
    body: "Log each customer request, give it an owner and a priority, and follow it from New to Resolved.",
    points: ["Internal comments on every request", "Status history you can trust", "Customer records with their requests and invoices"],
    image: "requests",
    focus: { x: 64, y: 52, zoom: 1.35 },
    alt: "The customer requests list with titles, customers, statuses and assignees",
  },
  {
    title: "Get paid",
    body: "Draft invoices with line items, tax and discounts, issue them, and record payments as they come in.",
    points: ["PDF invoices", "Partial payments and outstanding balances", "Overpayments and duplicate payments are refused"],
    image: "invoice",
    focus: { x: 50, y: 100, zoom: 1.5 },
    alt: "A paid invoice with its line items and totals",
  },
  {
    title: "Know your numbers",
    body: "Overview, employee, department and finance analytics, calculated from your live data and exportable to CSV or PDF.",
    points: ["Pick a period: this week, this month or your own range", "Workload by department", "Invoiced versus collected"],
    image: "analytics",
    focus: { x: 64, y: 52, zoom: 1.3 },
    alt: "The analytics page with overview figures and a department chart",
  },
  {
    title: "Bring your team",
    body: "Invite people by email with one of five roles. Change a role or remove someone's access whenever you need to.",
    points: ["Owner, manager, employee, accountant, customer support", "Each role sees only what it should", "Removed access keeps their history intact"],
    image: "members",
    focus: { x: 44, y: 46, zoom: 1.6 },
    alt: "The members settings page listing people, their roles and access",
  },
  {
    title: "Keep a record",
    body: "Important actions land in an activity log written in plain sentences, so you can always see who did what, and when.",
    points: ["Filtered to what each role may see", "Links straight to the record", "Kept even when a task is deleted"],
    image: "activity",
    focus: { x: 42, y: 42, zoom: 1.6 },
    alt: "The activity log with plain-sentence entries and times",
  },
] as const;

const CHAPTERS = [
  { label: "Overview", at: 13.5 },
  { label: "Planning", at: 19.5 },
  { label: "Support", at: 33.5 },
  { label: "Billing", at: 39 },
  { label: "Analytics", at: 45 },
  { label: "Team", at: 50.5 },
];

const TRUST = [
  { title: "Separate workspaces", body: "Every record belongs to one organization. Other organizations can't read it, or even tell that it exists." },
  { title: "Permissions checked on the server", body: "The five roles are enforced on every request, not just hidden in the interface." },
  { title: "Careful with money", body: "Exact decimal amounts, duplicate payments prevented, overpayments rejected." },
  { title: "Secure sign-in", body: "Server-side sessions, CSRF protection and rate-limited login." },
  { title: "An audit trail", body: "The activity log records who did what, and keeps it." },
  { title: "Tested", body: "More than 1,250 automated backend tests, including checks that one organization can never reach another's data." },
];

// A screenshot cropped in on the part the copy talks about: full app
// screens shrink to unreadable at feature size, especially on phones.
function FocusShot({ name, alt, focus }: { name: string; alt: string; focus: { x: number; y: number; zoom: number } }) {
  return (
    <div className="relative aspect-[16/10] overflow-hidden">
      <img
        src={`/landing/${name}.webp`}
        alt={alt}
        width={1600}
        height={1000}
        loading="lazy"
        decoding="async"
        className="absolute inset-0 h-full w-full object-cover"
        style={{ transform: `scale(${focus.zoom})`, transformOrigin: `${focus.x}% ${focus.y}%` }}
      />
    </div>
  );
}

function Shot({ name, alt, className, eager = false }: { name: string; alt: string; className?: string; eager?: boolean }) {
  return (
    <img
      src={`/landing/${name}.webp`}
      alt={alt}
      width={1600}
      height={1000}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      className={cn("block h-auto w-full", className)}
    />
  );
}

export function LandingPage() {
  const { status } = useAuth();
  const signedIn = status === "authenticated";
  const [tab, setTab] = useState<(typeof TOUR)[number]["id"]>("overview");
  const current = TOUR.find((t) => t.id === tab) ?? TOUR[0];
  const videoRef = useRef<HTMLVideoElement>(null);

  const playFrom = (seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    void video.play();
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ---------------- Header ---------------- */}
      <header className="sticky top-0 z-30 border-b border-border/70 bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/welcome" aria-label="FlowDesk home">
            <Logo />
          </Link>
          <nav aria-label="Sections" className="hidden items-center gap-7 text-sm font-medium text-foreground/75 md:flex">
            <a href="#features" className="hover:text-foreground">Features</a>
            <a href="#demo" className="hover:text-foreground">Demo</a>
            <a href="#security" className="hover:text-foreground">Security</a>
          </nav>
          <div className="flex items-center gap-2 sm:gap-3">
            {signedIn ? (
              <Link to="/" className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90">
                Open FlowDesk <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            ) : (
              <>
                <Link to="/login" className="inline-flex h-10 items-center rounded-md px-3 text-sm font-medium hover:bg-card">
                  Log in
                </Link>
                <Link to="/register" className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90">
                  <span className="sm:hidden">Sign up</span>
                  <span className="hidden sm:inline">Create your workspace</span>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        {/* ---------------- Hero ---------------- */}
        <section className="mx-auto max-w-6xl px-4 pb-10 pt-14 sm:px-6 sm:pt-20">
          <div className="max-w-3xl">
            <h1 className="text-[2.6rem] font-bold leading-[1.02] tracking-[-0.035em] sm:text-6xl lg:text-7xl">
              Run your whole business in one flow.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-relaxed text-foreground/75 sm:text-xl">
              FlowDesk brings tasks, customer requests, invoices and your team into one workspace, with the right
              access for everyone from the owner to customer support.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              {signedIn ? (
                <Link to="/" className="inline-flex h-12 items-center gap-2 rounded-md bg-primary px-6 text-base font-medium text-primary-foreground hover:opacity-90">
                  Open FlowDesk <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              ) : (
                <Link to="/register" className="inline-flex h-12 items-center gap-2 rounded-md bg-primary px-6 text-base font-medium text-primary-foreground hover:opacity-90">
                  Create your workspace <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              )}
              <a href="#demo" className="inline-flex h-12 items-center gap-2 rounded-md border border-border px-5 text-base font-medium hover:bg-card">
                <Play className="h-4 w-4" aria-hidden="true" /> Watch the 1-minute demo
              </a>
            </div>
            {!signedIn && (
              <p className="mt-4 text-sm text-foreground/60">
                Already have an account?{" "}
                <Link to="/login" className="font-medium text-primary hover:underline">
                  Log in
                </Link>
              </p>
            )}
          </div>
        </section>

        {/* The desk: folder tabs over the green blotter switch the screen. */}
        <section aria-label="Product tour" className="mx-auto max-w-6xl px-4 sm:px-6">
          <div role="tablist" aria-label="Screens" className="flex gap-1 overflow-x-auto pl-2 sm:pl-4">
            {TOUR.map((item) => {
              const active = item.id === tab;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  id={`tour-tab-${item.id}`}
                  aria-selected={active}
                  aria-controls="tour-panel"
                  onClick={() => setTab(item.id)}
                  className={cn(
                    "shrink-0 cursor-pointer rounded-t-lg px-4 py-2.5 text-sm font-semibold transition-colors",
                    active ? "bg-sidebar text-sidebar-foreground" : "bg-card text-foreground/65 hover:text-foreground",
                  )}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
          <div
            id="tour-panel"
            role="tabpanel"
            aria-labelledby={`tour-tab-${current.id}`}
            className="rounded-xl rounded-tl-none bg-sidebar p-3 shadow-[0_30px_60px_-20px_rgba(22,58,45,0.45)] sm:p-6"
          >
            <div className="overflow-hidden rounded-lg ring-1 ring-black/10">
              {TOUR.map((item) => (
                <div key={item.id} className={item.id === tab ? "block" : "hidden"}>
                  <Shot name={item.image} alt={`FlowDesk ${item.label.toLowerCase()} screen`} eager={item.id === "overview"} />
                </div>
              ))}
            </div>
            <p className="px-1 pb-1 pt-4 text-sm text-sidebar-foreground/85 sm:text-base" aria-live="polite">
              {current.caption}
            </p>
          </div>
        </section>

        {/* ---------------- The problem ---------------- */}
        <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
          <div className="grid gap-10 md:grid-cols-[1.1fr_1fr] md:items-center">
            <h2 className="text-3xl font-bold leading-tight tracking-[-0.025em] sm:text-5xl">
              Tasks here. Invoices there. Requests in someone&apos;s inbox.
            </h2>
            <div>
              <ul className="flex flex-wrap gap-2" aria-label="Tools FlowDesk replaces">
                {["Spreadsheets", "Email threads", "Team chat", "An invoicing app", "Sticky notes", "A to-do app"].map((tool) => (
                  <li key={tool} className="rounded-md border border-border bg-card px-3 py-1.5 text-sm text-foreground/55 line-through decoration-foreground/40">
                    {tool}
                  </li>
                ))}
              </ul>
              <p className="mt-6 text-lg leading-relaxed text-foreground/80">
                FlowDesk keeps the work, the customers and the money in one place, so nothing falls between tools and
                everyone sees the same picture.
              </p>
            </div>
          </div>
        </section>

        {/* ---------------- Features ---------------- */}
        <section id="features" className="scroll-mt-20 border-t border-border">
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
            <h2 className="max-w-2xl text-3xl font-bold tracking-[-0.025em] sm:text-4xl">Everything the business runs on</h2>
            <div className="mt-14 flex flex-col gap-20 sm:gap-28">
              {FEATURES.map((feature, i) => (
                <article key={feature.title} className="grid gap-8 md:grid-cols-2 md:items-center md:gap-14">
                  <div className={cn(i % 2 === 1 && "md:order-2")}>
                    <h3 className="text-2xl font-bold tracking-[-0.02em] sm:text-3xl">{feature.title}</h3>
                    <p className="mt-4 text-base leading-relaxed text-foreground/75 sm:text-lg">{feature.body}</p>
                    <ul className="mt-6 flex flex-col gap-3">
                      {feature.points.map((point) => (
                        <li key={point} className="flex gap-3 text-sm sm:text-base">
                          <span className="mt-2 h-1.5 w-4 shrink-0 rounded-full bg-warning" aria-hidden="true" />
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className={cn("overflow-hidden rounded-xl border border-border bg-card shadow-[0_24px_48px_-24px_rgba(22,58,45,0.35)]", i % 2 === 1 && "md:order-1")}>
                    <FocusShot name={feature.image} alt={feature.alt} focus={feature.focus} />
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ---------------- Demo ---------------- */}
        <section id="demo" className="scroll-mt-20 bg-sidebar text-sidebar-foreground">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-20 sm:px-6 sm:py-24 md:grid-cols-[1fr_1.1fr] md:items-center">
            <div>
              <h2 className="text-3xl font-bold tracking-[-0.025em] text-background sm:text-4xl">See it in a minute</h2>
              <p className="mt-4 text-lg leading-relaxed text-sidebar-foreground/85">
                A walk through a working day at Northbeam Digital, a made-up agency: planning, customer requests,
                billing, numbers and the team.
              </p>
              <ol className="mt-8 flex flex-col divide-y divide-white/10 border-y border-white/10" aria-label="Video chapters">
                {CHAPTERS.map((chapter) => (
                  <li key={chapter.label}>
                    <button
                      type="button"
                      onClick={() => playFrom(chapter.at)}
                      className="flex w-full cursor-pointer items-center justify-between py-3 text-left text-base font-medium hover:text-background"
                    >
                      {chapter.label}
                      <span className="text-sm tabular-nums text-sidebar-foreground/60">
                        0:{String(Math.floor(chapter.at)).padStart(2, "0")}
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
            <div className="mx-auto w-full max-w-md">
              <video
                ref={videoRef}
                className="aspect-[4/5] w-full rounded-xl bg-black/20 shadow-2xl"
                src="/landing/flowdesk-demo.mp4"
                poster="/landing/flowdesk-demo-poster.webp"
                controls
                playsInline
                muted
                preload="none"
                aria-label="FlowDesk product demo, about one minute, no sound"
              />
            </div>
          </div>
        </section>

        {/* ---------------- Security ---------------- */}
        <section id="security" className="scroll-mt-20">
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-24">
            <h2 className="max-w-2xl text-3xl font-bold tracking-[-0.025em] sm:text-4xl">Built to be trusted with the business</h2>
            <dl className="mt-12 grid gap-x-12 sm:grid-cols-2">
              {TRUST.map((item) => (
                <div key={item.title} className="border-t border-border py-6">
                  <dt className="text-lg font-semibold">{item.title}</dt>
                  <dd className="mt-2 text-base leading-relaxed text-foreground/75">{item.body}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* ---------------- Final call to action ---------------- */}
        <section className="px-4 pb-20 sm:px-6">
          <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 rounded-2xl bg-sidebar px-6 py-12 text-sidebar-foreground sm:px-12 sm:py-16 md:flex-row md:items-center md:justify-between">
            <h2 className="max-w-xl text-3xl font-bold tracking-[-0.025em] text-background sm:text-4xl">
              Bring your business into one flow.
            </h2>
            <div className="flex flex-wrap gap-3">
              {signedIn ? (
                <Link to="/" className="inline-flex h-12 items-center rounded-md bg-background px-6 text-base font-semibold text-foreground hover:opacity-90">
                  Open FlowDesk
                </Link>
              ) : (
                <>
                  <Link to="/register" className="inline-flex h-12 items-center rounded-md bg-background px-6 text-base font-semibold text-foreground hover:opacity-90">
                    Create your workspace
                  </Link>
                  <Link to="/login" className="inline-flex h-12 items-center rounded-md border border-white/25 px-6 text-base font-medium hover:bg-white/10">
                    Log in
                  </Link>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 text-sm text-foreground/60 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <Logo size={26} />
          <p>Built with Flask, React and PostgreSQL. Screens show Northbeam Digital, a fictional demo company.</p>
        </div>
      </footer>
    </div>
  );
}
