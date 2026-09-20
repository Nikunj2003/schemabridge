import Link from "next/link";
import { AuthorCredit } from "@/components/brand/author";
import { Wordmark } from "@/components/brand/logo";
import { HexGridBackground } from "@/components/marketing/hex-grid-background";
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
    <div className="marketing-page flex min-h-dvh flex-col">
      <SiteHeader />

      <main className="flex-1">
        <section className="marketing-hero relative overflow-hidden">
          <HexGridBackground />
          <div className="marketing-frame relative grid items-center gap-11 lg:grid-cols-[minmax(0,1fr)_minmax(22rem,28rem)] lg:gap-18">
            <div className="relative z-10">
              <p className="marketing-kicker">A careful path from spreadsheet to system</p>
              <h1 className="marketing-hero-title mt-4 max-w-[16ch] font-display">
                Make the first clean employee record.
              </h1>
              <p className="mt-5 max-w-[52ch] text-[16px] leading-relaxed text-ink-muted sm:text-[17px]">
                Hand over the exports your client actually sent you. SchemaBridge
                matches the columns, cleans what is safe to clean, and stops only
                when a choice would change what gets migrated.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
                <ButtonLink href="/signin" variant="primary" size="lg">
                  Start a migration
                </ButtonLink>
                <a href="#how" className="marketing-text-link text-[14px] font-medium text-ink-muted">
                  See how it works
                </a>
              </div>

              <p className="mt-5 text-[13px] text-ink-subtle">
                Free with synthetic data only. Up to 10 migrations a day.
              </p>
            </div>

            <div className="relative z-10 lg:justify-self-end">
              <MergeFigure />
            </div>
          </div>
        </section>

        <section id="how" className="marketing-section marketing-section-muted scroll-mt-16">
          <div className="marketing-frame">
            <div className="max-w-[48rem]">
              <p className="marketing-kicker">From raw files to a reviewable result</p>
              <h2 className="marketing-section-title mt-3 font-display">A migration with a clear next step</h2>
            </div>
            <ol className="marketing-steps mt-9 grid gap-7 sm:grid-cols-3 sm:gap-8">
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

        <section className="marketing-section">
          <div className="marketing-frame grid gap-12 lg:grid-cols-2 lg:gap-18">
            <DecisionList
              title="It decides on its own when it is safe to"
              points={[
                <>Matches <span className="raw">emp_nm</span>, <span className="raw">Employee Code</span> and <span className="raw">doj</span> onto the right fields without being told</>,
                "Combines rows for the same employee when the files agree",
                "Trims stray spaces, fixes casing, and writes dates one way",
                <>Keeps leading zeros — <span className="raw">000123</span> stays <span className="raw">000123</span></>,
                "Sends valid records to the destination and retries the ones that fail for a transient reason",
              ]}
            />
            <DecisionList
              title="It stops when guessing would be wrong"
              points={[
                <><span className="raw">03/04/2026</span> — that is two real dates, so it asks which one</>,
                "Two files with different start dates for the same employee",
                "A column nothing in the destination corresponds to",
                "An address that is still invalid after a repair was attempted",
                <>A record the destination itself refuses, with the destination&rsquo;s own reason shown</>,
              ]}
            />
          </div>
        </section>

        <section id="limits" className="marketing-section marketing-section-muted scroll-mt-16">
          <div className="marketing-frame">
            <div className="max-w-[48rem]">
              <p className="marketing-kicker">The boundary is part of the product</p>
              <h2 className="marketing-section-title mt-3 font-display">What it does not do</h2>
              <p className="mt-3 max-w-[58ch] text-[15px] leading-relaxed text-ink-muted">
                Plainly, so nothing here is a surprise later.
              </p>
            </div>
            <dl className="marketing-limits mt-9 grid gap-x-8 gap-y-7 sm:grid-cols-2 lg:grid-cols-4">
              <Limit term="It is a demo destination">
                Records go to a simulated HR system inside this app. Nothing is sent anywhere else.
              </Limit>
              <Limit term="Synthetic data only">
                Do not upload real personal information. Uploads are deleted after 48 hours.
              </Limit>
              <Limit term="Schemas need review">
                Build, import, or detect a target shape, then confirm its fields before relying on it for a client.
              </Limit>
              <Limit term="Small files">
                A few thousand rows at most — this is a workbench, not a batch pipeline.
              </Limit>
            </dl>
          </div>
        </section>
      </main>

      <footer className="marketing-footer border-t border-line">
        <div className="marketing-frame flex flex-col gap-5 py-7 sm:flex-row sm:items-center">
          <Wordmark withMark={false} />
          <p className="max-w-[44ch] text-[12.5px] text-ink-subtle sm:ml-2">
            A transparent workbench for employee-record migrations.
          </p>
          <div className="flex items-center gap-5 text-[13px] text-ink-muted sm:ml-auto">
            <a href="https://github.com/Nikunj2003/schemabridge" target="_blank" rel="noreferrer" className="marketing-nav-link">
              Source
            </a>
            <Link href="/signin" className="marketing-nav-link">Sign in</Link>
            <ThemeToggle />
          </div>
        </div>
        {/* Attribution on its own row under a divider. Folding it into the row
            above would have it competing with the product links for the same
            corner, and it is a different kind of statement. */}
        <div className="border-t border-line">
          <div className="marketing-frame py-4">
            <AuthorCredit />
          </div>
        </div>
      </footer>
    </div>
  );
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <li className="marketing-step">
      <span className="flex size-7 items-center justify-center rounded-full bg-accent-soft font-display text-[13px] font-semibold text-accent-ink">
        {n}
      </span>
      <h3 className="mt-4 text-[16px] font-semibold">{title}</h3>
      <p className="mt-2 text-[13.5px] leading-relaxed text-ink-muted">{body}</p>
    </li>
  );
}

function DecisionList({ title, points }: { title: string; points: React.ReactNode[] }) {
  return (
    <div>
      <h2 className="max-w-[23ch] font-display text-[24px] leading-[1.16] sm:text-[27px]">{title}</h2>
      <ul className="mt-5 space-y-3">
        {points.map((point, index) => <Point key={index}>{point}</Point>)}
      </ul>
    </div>
  );
}

function Point({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-3 text-[13.5px] leading-relaxed text-ink-muted">
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
      <dt className="text-[14px] font-semibold">{term}</dt>
      <dd className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">{children}</dd>
    </div>
  );
}
