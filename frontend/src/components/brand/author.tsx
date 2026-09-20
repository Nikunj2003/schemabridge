import { cn } from "@/lib/utils";

/**
 * Attribution, in the two places it belongs.
 *
 * One definition rather than two copies: the marketing footer and the workbench
 * strip carry the same three links, and a list maintained twice is a list where
 * one side eventually goes stale.
 *
 * Every link opens in a new tab with `rel="noreferrer"`. `noopener` comes free
 * with `target="_blank"` in current browsers, but `noreferrer` is the one worth
 * being explicit about — it stops the destination learning which page sent the
 * visitor.
 */

const AUTHOR = "Nikunj Khitha";

type AuthorLink = { href: string; label: string; icon: React.ReactNode };

const LINKS: AuthorLink[] = [
  { href: "https://nikunj.codenex.dev/", label: "Portfolio", icon: <IconGlobe /> },
  { href: "https://github.com/Nikunj2003", label: "GitHub", icon: <IconGitHub /> },
  { href: "https://www.linkedin.com/in/nikunj-khitha/", label: "LinkedIn", icon: <IconLinkedIn /> },
];

/** Full-width row for the public footer, where there is room for words. */
export function AuthorCredit({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-2", className)}>
      <p className="text-[12.5px] text-ink-subtle">
        Made by <span className="font-medium text-ink-muted">{AUTHOR}</span>
      </p>
      <ul className="flex items-center gap-x-4">
        {LINKS.map((link) => (
          <li key={link.href}>
            <a
              href={link.href}
              target="_blank"
              rel="noreferrer"
              className="marketing-nav-link inline-flex items-center gap-1.5 text-[13px] text-ink-muted"
            >
              <span className="text-ink-subtle">{link.icon}</span>
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The workbench strip: fixed alongside the header and rail, so it stays put while
 * the work area scrolls.
 *
 * Labels are hidden below `sm` rather than the row wrapping. A strip that changed
 * height would shift the scroll area under someone mid-read, and on a phone the
 * icons still carry an accessible name.
 */
export function AuthorStrip() {
  return (
    <footer className="flex h-9 shrink-0 items-center gap-3 border-t border-line bg-surface px-4 sm:px-6">
      <p className="truncate text-[12px] text-ink-subtle">
        Made by <span className="font-medium text-ink-muted">{AUTHOR}</span>
      </p>
      <ul className="ml-auto flex items-center gap-1">
        {LINKS.map((link) => (
          <li key={link.href}>
            <a
              href={link.href}
              target="_blank"
              rel="noreferrer"
              title={link.label}
              className="flex items-center gap-1.5 rounded px-2 py-1 text-[12px] text-ink-muted transition-colors hover:bg-sunken hover:text-ink"
            >
              <span className="text-ink-subtle">{link.icon}</span>
              <span className="hidden sm:inline">{link.label}</span>
              <span className="sr-only sm:hidden">{link.label}</span>
            </a>
          </li>
        ))}
      </ul>
    </footer>
  );
}

/* Icons: 14px on their source grid, matching the 12px text they sit beside. */

function IconGlobe() {
  return (
    <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17M12 3.5c2.2 2.3 3.3 5.1 3.3 8.5s-1.1 6.2-3.3 8.5c-2.2-2.3-3.3-5.1-3.3-8.5S9.8 5.8 12 3.5Z" />
    </svg>
  );
}

function IconGitHub() {
  return (
    <svg viewBox="0 0 24 24" className="size-3.5" fill="currentColor" aria-hidden>
      <path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02a9.5 9.5 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0 0 12 2Z" />
    </svg>
  );
}

function IconLinkedIn() {
  return (
    <svg viewBox="0 0 24 24" className="size-3.5" fill="currentColor" aria-hidden>
      <path d="M4.98 3.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM3 9.5h4v11.5H3V9.5Zm6.5 0h3.83v1.57h.05a4.2 4.2 0 0 1 3.78-2.07c4.04 0 4.79 2.66 4.79 6.12V21h-4v-5.1c0-1.22-.02-2.78-1.7-2.78-1.7 0-1.96 1.33-1.96 2.7V21h-4V9.5Z" />
    </svg>
  );
}
