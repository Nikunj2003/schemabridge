"use client";

import { AllowanceMeter } from "@/components/app/shell";
import { ContentFrame } from "@/components/app/content-frame";
import { useMigrationUsage } from "@/components/app/migration-usage";

/** What this browser session can start, plus the synthetic-data retention policy. */
export default function UsagePage() {
  const { usage, error } = useMigrationUsage();
  return (
    <ContentFrame>
      <h1 className="font-display text-[24px]">Usage &amp; data</h1>
      <p className="mt-1.5 max-w-[62ch] text-[14px] text-ink-muted">
        The migration allowance keeps this synthetic-data workbench available for everyone.
      </p>

      <section className="panel mt-6 max-w-[32rem] px-5 py-4">
        <h2 className="text-[14px] font-semibold">Migrations in this browser session today</h2>
        {usage ? (
          <p className="mt-1 font-display text-[28px] tnum">
            {usage.used}<span className="text-[16px] text-ink-muted"> of {usage.limit} started</span>
          </p>
        ) : <p className="mt-2 text-[13.5px] text-ink-muted">{error ?? "Loading allowance…"}</p>}
        <div className="mt-3"><AllowanceMeter usage={usage} error={error} /></div>
        <p className="mt-3 text-[12.5px] text-ink-muted">This is tied to this browser until sign-in is available.</p>
      </section>

      <section className="panel mt-4 max-w-[42rem] px-5 py-4">
        <h2 className="text-[14px] font-semibold">What is stored</h2>
        <p className="mt-2 max-w-[62ch] text-[13.5px] text-ink-muted">
          The files you upload, the records built from them and the decisions you made are kept for 48 hours so you can reopen a migration, then deleted. Use synthetic data only — do not upload real personal information.
        </p>
      </section>
    </ContentFrame>
  );
}
