"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId, useState } from "react";
import { Wordmark } from "@/components/brand/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ReactNode; exact?: boolean };

const WORKSPACE: NavItem[] = [
  { href: "/app", label: "Migrations", icon: <IconStack />, exact: true },
  { href: "/app/new", label: "New migration", icon: <IconPlus /> },
];

const REFERENCE: NavItem[] = [
  { href: "/app/schema", label: "My schema", icon: <IconSchema /> },
  { href: "/app/usage", label: "Usage & data", icon: <IconGauge /> },
];

/**
 * The signed-in frame.
 *
 * The header and rail are fixed and only the work area scrolls. Losing the
 * navigation mid-scroll — and with it the run's context and the way out — was
 * the single most disorienting thing about the previous build.
 */
export function AppShell({
  children,
  account,
  usage,
}: {
  children: React.ReactNode;
  account: { name: string; email: string };
  usage: { runsUsed: number; runsLimit: number };
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    // h-dvh with overflow-hidden: the page itself never scrolls, so the chrome
    // cannot travel off the top of the viewport.
    <div className="flex h-dvh overflow-hidden bg-canvas">
      <aside className="hidden w-[228px] shrink-0 flex-col border-r border-line bg-surface md:flex">
        <div className="flex h-14 shrink-0 items-center px-4">
          <Link href="/app" className="rounded-md">
            <Wordmark />
          </Link>
        </div>

        <nav className="scroll-area flex-1 px-2.5 py-3" aria-label="Main">
          <NavGroup label="Workspace" items={WORKSPACE} pathname={pathname} />
          <NavGroup label="Reference" items={REFERENCE} pathname={pathname} className="mt-5" />
        </nav>

        <div className="shrink-0 border-t border-line p-2.5">
          <AllowanceMeter used={usage.runsUsed} limit={usage.runsLimit} />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface px-4 sm:px-6">
          <Link href="/app" className="md:hidden">
            <Wordmark />
          </Link>
          <div className="flex-1" />
          <ThemeToggle />
          <AccountMenu account={account} open={menuOpen} setOpen={setMenuOpen} />
        </header>

        {/* Phone navigation: the rail becomes a strip, still outside the scroll. */}
        <nav
          className="flex shrink-0 gap-1 overflow-x-auto border-b border-line bg-surface px-2 py-1.5 md:hidden"
          aria-label="Main"
        >
          {[...WORKSPACE, ...REFERENCE].map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} compact />
          ))}
        </nav>

        <main className="scroll-area flex-1">{children}</main>
      </div>
    </div>
  );
}

function NavGroup({
  label,
  items,
  pathname,
  className,
}: {
  label: string;
  items: NavItem[];
  pathname: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <p className="eyebrow px-2.5 pb-1.5">{label}</p>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item.href}>
            <NavLink item={item} pathname={pathname} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A run lives under /app/migrations/… but belongs to "Migrations". */
function isActive(item: NavItem, pathname: string): boolean {
  if (item.href === "/app") return pathname === "/app" || pathname.startsWith("/app/migrations");
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

function NavLink({
  item,
  pathname,
  compact = false,
}: {
  item: NavItem;
  pathname: string;
  compact?: boolean;
}) {
  const active = isActive(item, pathname);
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-md text-[13.5px] font-medium transition-colors",
        compact ? "shrink-0 px-2.5 py-1.5" : "px-2.5 py-2",
        active
          ? "bg-accent-soft text-accent-ink"
          : "text-ink-muted hover:bg-sunken hover:text-ink",
      )}
    >
      <span className={cn("shrink-0", active ? "text-accent" : "text-ink-subtle")}>{item.icon}</span>
      {item.label}
    </Link>
  );
}

/** How much is left, and exactly when it comes back. */
export function AllowanceMeter({ used, limit }: { used: number; limit: number }) {
  const left = Math.max(0, limit - used);
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <div className="rounded-md bg-sunken px-3 py-2.5">
      <p className="text-[13px] font-medium tnum">
        {left} of {limit} migrations left
      </p>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-line-strong">
        <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1.5 text-[12px] text-ink-subtle">Resets at 12:00 AM IST</p>
    </div>
  );
}

function AccountMenu({
  account,
  open,
  setOpen,
}: {
  account: { name: string; email: string };
  open: boolean;
  setOpen: (value: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="relative">
      <button
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-md py-1 pl-1 pr-1.5 text-[13.5px] hover:bg-sunken"
      >
        <span className="flex size-7 items-center justify-center rounded-full bg-accent-soft text-[12px] font-semibold text-accent-ink">
          {account.name.slice(0, 1)}
        </span>
        <span className="hidden max-w-[14ch] truncate sm:inline">{account.name}</span>
        <IconChevron />
      </button>

      {open && (
        <>
          {/* Clicking anywhere else closes it, including on touch. */}
          <button
            className="fixed inset-0 z-10 cursor-default"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
          />
          <div
            id={id}
            className="panel absolute right-0 top-full z-20 mt-1.5 w-56 p-1 shadow-pop"
          >
            <div className="px-2.5 py-2">
              <p className="text-[13.5px] font-medium">{account.name}</p>
              <p className="truncate text-[12.5px] text-ink-muted">{account.email}</p>
            </div>
            <div className="my-1 h-px bg-line" />
            <Link href="/app/usage" className="block rounded px-2.5 py-1.5 text-[13.5px] hover:bg-sunken">
              Usage &amp; data
            </Link>
            <Link href="/app/schema" className="block rounded px-2.5 py-1.5 text-[13.5px] hover:bg-sunken">
              My schema
            </Link>
            <div className="my-1 h-px bg-line" />
            <Link href="/" className="block rounded px-2.5 py-1.5 text-[13.5px] hover:bg-sunken">
              Sign out
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

/* Icons: drawn inline at 16px on a 24px grid, so they align with 13.5px text. */

function IconStack() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7.5 12 3.5l8 4-8 4z" />
      <path d="m4 12.5 8 4 8-4M4 17l8 4 8-4" opacity=".55" />
    </svg>
  );
}

function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function IconSchema() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3.5" y="4" width="17" height="16" rx="2" />
      <path d="M3.5 9h17M9 9v11" opacity=".55" />
    </svg>
  );
}

function IconGauge() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 18a8 8 0 1 1 16 0" />
      <path d="m12 14 3.5-3.5" />
    </svg>
  );
}

function IconChevron() {
  return (
    <svg viewBox="0 0 24 24" className="size-3.5 text-ink-subtle" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}
