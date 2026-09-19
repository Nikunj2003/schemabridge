import Link from "next/link";
import { Wordmark } from "@/components/brand/logo";
import { MergeFigure } from "@/components/marketing/merge-figure";
import { SiteHeader } from "@/components/marketing/site-header";
import { ButtonLink } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

/**
 * The public page.
 *
 * It answers the two questions someone has before signing in: what does this
 * take, and where do the records end up. No upload box, no invented metrics,
 * no customer logos — the demonstration is the product's actual behaviour.
 */
export default function LandingPage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />

      <main className="flex-1">
        <section className="mx-auto max-w-[70rem] px-4 pt-14 pb-16 sm:px-8 sm:pt-20">
          <div className="grid items-center gap-10 lg:grid-cols-[1fr_minmax(0,26rem)] lg:gap-14">
            <div>
              <p className="eyebrow">Employee data migration</p>
              <h1 className="mt-3 max-w-[22ch] font-display text-[34px] leading-[1.1] sm:text-[44px]">
                Bring messy employee files together.
              </h1>
              <p className="mt-4 max-w-[46ch] text-[16px] leading-relaxed text-ink-muted">
                Hand over the exports your client actually sent you. The agent
                matches the columns, cleans what is safe to clean, and stops to
                ask you only when a choice would change what gets migrated.
              </p>

              <div className="mt-7 flex flex-wrap items-center gap-3">
                <ButtonLink href="/signin" variant="primary" size="lg">
                  Get started
                </ButtonLink>
                <a
                  href="#how"
                  className="text-[14px] font-medium text-ink-muted underline-offset-4 hover:text-ink hover:underline"
                >
                  See how it works
                </a>
              </div>

              <p className="mt-4 text-[13px] text-ink-subtle">
                Free, synthetic data only, 10 migrations a day.
              </p>
            </div>

            <MergeFigure />
          </div>
        </section>

        <section id="how" className="border-y border-line bg-surface">
          <div className="mx-auto max-w-[70rem] px-4 py-14 sm:px-8">
            <h2 className="font-display text-[24px]">How it works</h2>
            <ol className="mt-7 grid gap-6 sm:grid-cols-3">
              <Step
                n={1}
                title="Add the exports"
                body="CSV or Excel, more than one at a time. Different column names in each file are expected, not a problem."
              />
              <Step
                n={2}
                title="Watch it work"
                body="Columns matched, duplicate rows combined, dates and spellings standardised — every step recorded with its reason."
              />
              <Step
                n={3}
                title="Answer what it cannot decide"
                body="Two files disagree about a start date? It asks you, shows both sources side by side, and does nothing until you choose."
              />
            </ol>
          </div>
        </section>

        <section className="mx-auto max-w-[70rem] px-4 py-14 sm:px-8">
          <div className="grid gap-8 lg:grid-cols-2 lg:gap-14">
            <div>
              <h2 className="font-display text-[22px]">It decides on its own when it is safe to</h2>
              <ul className="mt-4 space-y-2.5">
                <Point>Matches <span className="raw">emp_nm</span>, <span className="raw">Employee Code</span> and <span className="raw">doj</span> onto the right fields without being told</Point>
                <Point>Combines rows for the same employee when the files agree</Point>
                <Point>Trims stray spaces, fixes casing, and writes dates one way</Point>
                <Point>Keeps leading zeros — <span className="raw">000123</span> stays <span className="raw">000123</span></Point>
                <Point>Sends valid records to the destination and retries the ones that fail for a transient reason</Point>
              </ul>
            </div>

            <div>
              <h2 className="font-display text-[22px]">It stops when guessing would be wrong</h2>
              <ul className="mt-4 space-y-2.5">
                <Point><span className="raw">03/04/2026</span> — that is two real dates, so it asks which one</Point>
                <Point>Two files with different start dates for the same employee</Point>
                <Point>A column nothing in the destination corresponds to</Point>
                <Point>An address that is still invalid after a repair was attempted</Point>
                <Point>A record the destination itself refuses, with the destination&rsquo;s own reason shown</Point>
              </ul>
            </div>
          </div>
        </section>

        <section id="limits" className="border-t border-line bg-surface">
          <div className="mx-auto max-w-[70rem] px-4 py-14 sm:px-8">
            <h2 className="font-display text-[22px]">What it does not do</h2>
            <p className="mt-2 max-w-[62ch] text-[14px] text-ink-muted">
              Plainly, so nothing here is a surprise later.
            </p>
            <dl className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Limit term="It is a demo destination">
                Records go to a simulated HR system inside this app. Nothing is sent anywhere else.
              </Limit>
              <Limit term="Synthetic data only">
                Do not upload real personal information. Uploads are deleted after 48 hours.
              </Limit>
              <Limit term="Employee records only">
                One fixed destination shape. It does not learn arbitrary schemas.
              </Limit>
              <Limit term="Small files">
                A few thousand rows at most — this is a workbench, not a batch pipeline.
              </Limit>
            </dl>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[70rem] flex-col gap-4 px-4 py-7 sm:flex-row sm:items-center sm:px-8">
          <Wordmark withMark={false} />
          <div className="flex items-center gap-5 text-[13px] text-ink-muted sm:ml-auto">
            <a
              href="https://github.com/Nikunj2003/schemabridge"
              target="_blank"
              rel="noreferrer"
              className="hover:text-ink"
            >
              Source
            </a>
            <Link href="/signin" className="hover:text-ink">
              Sign in
            </Link>
            <ThemeToggle />
          </div>
        </div>
      </footer>
    </div>
  );
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <li>
      <span className="flex size-7 items-center justify-center rounded-full bg-accent-soft font-display text-[13px] font-semibold text-accent-ink">
        {n}
      </span>
      <h3 className="mt-3 text-[15.5px] font-semibold">{title}</h3>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-muted">{body}</p>
    </li>
  );
}

function Point({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-2.5 text-[13.5px] leading-relaxed text-ink-muted">
      <svg viewBox="0 0 16 16" className="mt-1 size-3.5 shrink-0 text-accent" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
        <path d="M3 8.5l3.5 3.5L13 4" />
      </svg>
      <span>{children}</span>
    </li>
  );
}

function Limit({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[13.5px] font-semibold">{term}</dt>
      <dd className="mt-1 text-[13px] leading-relaxed text-ink-muted">{children}</dd>
    </div>
  );
}
