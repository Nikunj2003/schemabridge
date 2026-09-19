import { UsageSummary } from "@/components/app/shell";
import { USAGE } from "@/lib/sample";

export default function UsagePage() {
  return (
    <div className="mx-auto max-w-2xl px-5 py-8 sm:px-8 sm:py-10">
      <h1 className="font-display text-[26px] font-semibold">Usage &amp; data</h1>

      <div className="mt-6 space-y-6">
        <div className="md:hidden">
          <UsageSummary />
        </div>

        <section className="card p-5">
          <h2 className="text-[15.5px] font-semibold">Your allowance today</h2>
          <dl className="mt-3 space-y-2 text-[14px]">
            <Row label="Migrations started" value={`${USAGE.runsUsed} of ${USAGE.runsLimit}`} />
            <Row label="AI questions asked" value={`${USAGE.aiUsed} of ${USAGE.aiLimit}`} />
            <Row label="Resets" value="12:00 AM IST" />
          </dl>
          <p className="mt-3 text-[13px] leading-relaxed text-ink-muted">
            Reviewing, answering questions and retrying a delivery on a migration
            you already started do not count against your migrations.
          </p>
        </section>

        <section className="card p-5">
          <h2 className="text-[15.5px] font-semibold">Your data</h2>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
            Uploaded files and everything derived from them are kept for 48 hours
            so you can come back to a migration, then deleted. You can remove a
            migration sooner from its own page.
          </p>
          <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">
            This is a demonstration on made-up data, and records go to a simulated
            HR system. Please do not upload anyone&rsquo;s real details.
          </p>
        </section>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line pb-2 last:border-0">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
