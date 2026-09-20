import Link from "next/link";
import { Wordmark } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

const LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#limits", label: "Limits" },
];

export function SiteHeader() {
  return (
    <header className="marketing-header sticky top-0 z-30 border-b border-line bg-canvas/88 backdrop-blur-md">
      <div className="marketing-frame flex h-15 items-center gap-5">
        <Link href="/" aria-label="SchemaBridge home" className="shrink-0">
          <Wordmark />
        </Link>

        <nav aria-label="Marketing" className="ml-auto hidden items-center gap-6 text-[13px] text-ink-muted sm:flex">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} className="marketing-nav-link">
              {link.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:ml-1">
          <ThemeToggle />
          <ButtonLink href="/signin" variant="primary" size="sm">
            Sign in
          </ButtonLink>
        </div>
      </div>
    </header>
  );
}
