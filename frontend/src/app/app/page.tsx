import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { Badge, Dot, type Tone } from "@/components/ui/status";
import { HISTORY, type HistoryRow } from "@/lib/sample";

const STATE: Record<HistoryRow["state"], { tone: Tone; label: string }> = {
  "needs-you": { tone: "attention", label: "Needs you" },
  running: { tone: "working", label: "Working" },
  done: { tone: "ok", label: "Done" },
  "done-with-problems": { tone: "problem", label: "Done, 1 problem" },
};

export default function MigrationsPage() {
  return (
    <div className="mx-auto max-w-4xl px-5 py-8 sm:px-8 sm:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[26px] font-semibold">Your migrations</h1>
          <p className="mt-1.5 text-[14.5px] text-ink-muted">
            Pick up where you left off, or start a new one.
          </p>
        </div>
        <ButtonLink href="/app/new" variant="primary">
          New migration
        </ButtonLink>
      </div>

      <ul className="mt-7 space-y-3">
        {HISTORY.map((run) => {
          const state = STATE[run.state];
          return (
            <li key={run.id}>
              <Link
                href={`/app/migrations/${run.id}`}
                className="card block p-4 transition-colors hover:border-line-strong"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-[16px] font-semibold">{run.name}</h2>
                    <p className="mt-1 truncate text-[13.5px] text-ink-muted">
                      {run.files.join(" · ")}
                    </p>
                  </div>
                  <Badge tone={state.tone}>
                    <Dot tone={state.tone} busy={run.state === "running"} />
                    {state.label}
                  </Badge>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13.5px] text-ink-muted">
                  <span>{run.summary}</span>
                  <span className="text-ink-subtle">{run.when}</span>
                  <span className="ml-auto font-medium text-accent">
                    {run.state === "needs-you" ? "Continue review" : "Open"}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>

      <section className="mt-10">
        <h2 className="text-[15px] font-semibold">Nothing to hand?</h2>
        <p className="mt-1.5 text-[14px] text-ink-muted">
          Start from sample files instead of hunting for a spreadsheet.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <SampleCard
            title="A clean import"
            body="Three employees, tidy columns. Runs start to finish without asking you anything."
            href="/app/migrations/sample-clean"
          />
          <SampleCard
            title="An import with questions"
            body="Two exports that disagree: a duplicate, an ambiguous date and an address that cannot be fixed."
            href="/app/migrations/mig-4821"
          />
        </div>
      </section>

      <p className="mt-10 text-[13px] text-ink-muted">
        Migrations are kept for 48 hours, then deleted. You can remove one sooner
        from its own page.
      </p>
    </div>
  );
}

function SampleCard({ title, body, href }: { title: string; body: string; href: string }) {
  return (
    <Link href={href} className="card block p-4 transition-colors hover:border-line-strong">
      <h3 className="text-[15px] font-semibold">{title}</h3>
      <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-muted">{body}</p>
      <p className="mt-3 text-[13.5px] font-medium text-accent">Try this</p>
    </Link>
  );
}
