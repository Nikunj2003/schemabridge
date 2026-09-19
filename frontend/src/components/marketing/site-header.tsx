"use client";

import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-5 sm:px-8">
        <Link href="/" className="flex items-center gap-2 font-display text-[17px] font-semibold tracking-tight">
          <Bridge />
          SchemaBridge
        </Link>

        <nav className="ml-2 hidden items-center gap-5 text-[14px] text-ink-muted md:flex">
          <Link href="#how" className="hover:text-ink">
            How it works
          </Link>
          <Link href="/example" className="hover:text-ink">
            Example
          </Link>
          <Link href="#limits" className="hover:text-ink">
            Limits
          </Link>
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-2">
          {/* The theme control needs ~108px, which a 390px header cannot spare
              alongside the primary action. It reappears in the footer there. */}
          <span className="hidden sm:inline">
            <ThemeToggle />
          </span>
          <ButtonLink href="/app" size="sm" variant="primary">
            Sign in
          </ButtonLink>
        </div>
      </div>
    </header>
  );
}

/** Two rails meeting — the product's one piece of iconography. */
function Bridge() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 text-accent" aria-hidden>
      <path
        d="M3 16c3.5 0 4.5-8 9-8s5.5 8 9 8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path d="M3 16h18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" opacity="0.35" />
    </svg>
  );
}
