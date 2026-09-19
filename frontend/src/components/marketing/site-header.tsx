import Link from "next/link";
import { Wordmark } from "@/components/brand/logo";
import { ButtonLink } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

const LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#limits", label: "What it does not do" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[70rem] items-center gap-6 px-4 sm:px-8">
        <Link href="/">
          <Wordmark />
        </Link>

        <nav className="ml-auto hidden items-center gap-6 text-[13.5px] text-ink-muted sm:flex">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} className="hover:text-ink">
              {link.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:ml-0">
          <ThemeToggle />
          <ButtonLink href="/signin" variant="primary" size="sm">
            Sign in
          </ButtonLink>
        </div>
      </div>
    </header>
  );
}
