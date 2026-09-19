import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { SiteHeader } from "@/components/marketing/site-header";
import { MergeFigure } from "@/components/marketing/merge-figure";
import { ThemeToggle } from "@/components/theme-toggle";

export const metadata = {
  title: "SchemaBridge — bring messy employee files together",
  description:
    "SchemaBridge reads several employee exports, works out how they fit the target schema, cleans what it safely can, and asks you only about the decisions that need judgment.",
};

export default function LandingPage() {
  return (
    <>
      <SiteHeader />

      <main>
        <section className="mx-auto max-w-6xl px-5 pt-14 pb-16 sm:px-8 sm:pt-20">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center lg:gap-16">
            <div className="max-w-xl">
              <h1 className="font-display text-[34px] leading-[1.08] font-semibold sm:text-[44px]">
                Bring messy employee files together. Review only what needs your judgment.
              </h1>

              <p className="mt-5 text-[16px] leading-relaxed text-ink-muted">
                Drop in the exports a client sends you — different column names,
                dates in three formats, the same person twice. SchemaBridge works
                out how they fit your employee record, fixes what it can prove is
                safe, and sends the result to your HR system. It stops to ask you
                only when a decision genuinely needs a person.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-3">
                <ButtonLink href="/app" variant="primary" size="lg">
                  <GoogleMark />
                  Continue with Google
                </ButtonLink>
                <ButtonLink href="/example" size="lg">
                  See a worked example
                </ButtonLink>
              </div>

              <p className="mt-4 text-[13px] text-ink-muted">
                Free, and the only sign-in is Google. Use the built-in sample files
                if you have nothing to hand.
              </p>
            </div>

            <MergeFigure />
          </div>
        </section>

        <section id="how" className="border-y border-line bg-surface">
          <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8">
            <h2 className="font-display text-[24px] font-semibold">How a migration goes</h2>
            <ol className="mt-8 grid gap-8 md:grid-cols-3">
              <Step
                n={1}
                title="Add the exports"
                body="CSV or Excel, up to three files. They do not need matching column names, and you do not map anything by hand."
              />
              <Step
                n={2}
                title="Watch it work"
                body="You see each step as it happens: columns matched, duplicates combined, dates standardised — each with the reason."
              />
              <Step
                n={3}
                title="Answer what is left"
                body="Usually a handful of questions, each showing both source files side by side so you can answer without opening the spreadsheet."
              />
            </ol>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-5 py-14 sm:px-8">
          <div className="grid gap-10 md:grid-cols-2">
            <div>
              <h2 className="font-display text-[22px] font-semibold">Handled without asking</h2>
              <ul className="mt-4 space-y-2.5 text-[14.5px] text-ink-muted">
                <Item>Column names it recognises, however they are spelled</Item>
                <Item>Extra spaces, inconsistent casing, dates in a clear format</Item>
                <Item>The same employee in two files, where the files agree</Item>
                <Item>Sending each finished record and retrying if the system is briefly busy</Item>
              </ul>
            </div>
            <div>
              <h2 className="font-display text-[22px] font-semibold">Brought to you</h2>
              <ul className="mt-4 space-y-2.5 text-[14.5px] text-ink-muted">
                <Item>A date that could be read two ways, like 03/04/2026</Item>
                <Item>Two files that disagree about the same employee</Item>
                <Item>A column whose name could mean two different fields</Item>
                <Item>A value no safe rule can repair, like a malformed address</Item>
              </ul>
              <p className="mt-4 text-[13.5px] text-ink-muted">
                It never guesses at one of these, and it never asks you about
                something it can prove.
              </p>
            </div>
          </div>
        </section>

        <section id="limits" className="border-t border-line bg-surface">
          <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8">
            <h2 className="font-display text-[20px] font-semibold">What this is</h2>
            <div className="mt-4 grid gap-x-10 gap-y-3 text-[14px] text-ink-muted sm:grid-cols-2">
              <p>
                A working demonstration on made-up data. The destination is a
                simulated HR system, so nothing reaches a real one.
              </p>
              <p>
                Please use the sample files or your own invented data. Do not
                upload anyone&rsquo;s real personal information.
              </p>
              <p>
                Files are read in your browser session and kept for 48 hours so you
                can come back to a migration, then deleted.
              </p>
              <p>
                Ten migrations a day per person, so the shared free capacity lasts.
                Your allowance resets at midnight IST.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-5 gap-y-2 px-5 py-8 text-[13px] text-ink-muted sm:px-8">
        <span>SchemaBridge</span>
        <Link href="/example" className="hover:text-ink">
          Worked example
        </Link>
        <a
          href="https://github.com/Nikunj2003/schemabridge"
          className="hover:text-ink"
          target="_blank"
          rel="noreferrer"
        >
          Source
        </a>
        <span className="ml-auto flex items-center gap-4">
          <span className="sm:hidden">
            <ThemeToggle />
          </span>
          <span className="hidden sm:inline">Built with AI coding tools.</span>
        </span>
      </footer>
    </>
  );
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <li>
      {/* Numbered because this genuinely is a sequence. */}
      <span className="flex size-7 items-center justify-center rounded-full border border-accent/30 bg-accent-soft text-[13px] font-semibold text-accent-ink">
        {n}
      </span>
      <h3 className="mt-3 text-[16px] font-semibold">{title}</h3>
      <p className="mt-1.5 text-[14.5px] leading-relaxed text-ink-muted">{body}</p>
    </li>
  );
}

function Item({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <svg viewBox="0 0 16 16" className="mt-[7px] size-3.5 shrink-0 text-accent" aria-hidden>
        <path d="M2 8.5l4 4 8-9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span>{children}</span>
    </li>
  );
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 18 18" className="size-4" aria-hidden>
      <path
        fill="currentColor"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92a8.78 8.78 0 0 0 2.68-6.62Z"
        opacity="0.95"
      />
      <path
        fill="currentColor"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86a5.4 5.4 0 0 1-5.07-3.73H.96v2.34A8.99 8.99 0 0 0 9 18Z"
        opacity="0.75"
      />
      <path
        fill="currentColor"
        d="M3.93 10.69a5.41 5.41 0 0 1 0-3.38V4.96H.96a9 9 0 0 0 0 8.08l2.97-2.35Z"
        opacity="0.55"
      />
      <path
        fill="currentColor"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A8.99 8.99 0 0 0 .96 4.96l2.97 2.35A5.4 5.4 0 0 1 9 3.58Z"
        opacity="0.95"
      />
    </svg>
  );
}
