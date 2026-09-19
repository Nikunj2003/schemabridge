"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";
import { USAGE, ACCOUNT } from "@/lib/sample";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/app", label: "My migrations" },
  { href: "/app/new", label: "New migration" },
  { href: "/app/usage", label: "Usage & data" },
];

/**
 * The signed-in frame.
 *
 * Navigation and account sit still while the work area changes, so someone deep
 * in a decision always knows where they are and how much allowance is left.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-line bg-canvas/90 px-4 backdrop-blur sm:px-6">
        <Link href="/app" className="flex items-center gap-2 font-display text-[16px] font-semibold tracking-tight">
          <svg viewBox="0 0 24 24" className="size-5 text-accent" aria-hidden>
            <path d="M3 16c3.5 0 4.5-8 9-8s5.5 8 9 8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path d="M3 16h18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.35" />
          </svg>
          SchemaBridge
        </Link>

        <div className="flex-1" />
        <ThemeToggle />
        <details className="relative">
          <summary className="flex cursor-pointer list-none items-center gap-2 rounded-md px-2 py-1.5 text-[13.5px] hover:bg-sunken [&::-webkit-details-marker]:hidden">
            <span className="flex size-7 items-center justify-center rounded-full bg-accent-soft text-[12px] font-semibold text-accent-ink">
              {ACCOUNT.name.slice(0, 1)}
            </span>
            <span className="hidden sm:inline">{ACCOUNT.name}</span>
          </summary>
          <div className="card absolute right-0 top-full mt-1 w-60 p-1 text-[13.5px]">
            <p className="px-3 py-2 text-ink-muted">{ACCOUNT.email}</p>
            <Link href="/app/usage" className="block rounded px-3 py-2 hover:bg-sunken">
              Usage &amp; data
            </Link>
            <Link href="/" className="block rounded px-3 py-2 hover:bg-sunken">
              Sign out
            </Link>
          </div>
        </details>
      </header>

      <div className="mx-auto flex w-full max-w-[1400px] flex-1 flex-col md:flex-row">
        {/* Horizontal on a phone, a rail on desktop: a fixed 280px sidebar would
            leave nothing for the actual work at 390px wide. */}
        <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 md:w-56 md:shrink-0 md:flex-col md:overflow-visible md:border-b-0 md:border-r md:px-3 md:py-5">
          {NAV.map((item) => {
            // A run lives under /app/migrations/… but belongs to "My migrations",
            // so that entry stays marked while someone is inside a migration.
            const active =
              item.href === "/app"
                ? pathname === "/app" || pathname.startsWith("/app/migrations")
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "shrink-0 rounded-md px-3 py-2 text-[14px] font-medium transition-colors",
                  active ? "bg-accent-soft text-accent-ink" : "text-ink-muted hover:bg-sunken hover:text-ink",
                )}
              >
                {item.label}
              </Link>
            );
          })}

          <div className="ml-auto hidden md:mt-auto md:ml-0 md:block">
            <UsageSummary />
          </div>
        </nav>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

/** How much is left, and exactly when it comes back. */
export function UsageSummary() {
  const left = USAGE.runsLimit - USAGE.runsUsed;
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <p className="text-[13px] font-medium">
        {left} of {USAGE.runsLimit} migrations left today
      </p>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-sunken">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${(USAGE.runsUsed / USAGE.runsLimit) * 100}%` }}
        />
      </div>
      <p className="mt-2 text-[12px] text-ink-muted">Resets at 12:00 AM IST</p>
    </div>
  );
}
