import { AllowanceMeter } from "@/components/app/shell";
import { ACCOUNT, USAGE } from "@/lib/account";

/** What has been used, what is kept, and for how long. */
export default function UsagePage() {
  return (
    <div className="mx-auto max-w-[52rem] px-4 py-6 sm:px-8 sm:py-8">
      <h1 className="font-display text-[24px]">Usage &amp; data</h1>
      <p className="mt-1.5 text-[14px] text-ink-muted">
        Limits exist so one person cannot exhaust the shared model allowance.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <section className="panel px-5 py-4">
          <h2 className="text-[14px] font-semibold">Migrations today</h2>
          <p className="mt-1 font-display text-[28px] tnum">
            {USAGE.runsUsed}
            <span className="text-[16px] text-ink-muted"> of {USAGE.runsLimit}</span>
          </p>
          <div className="mt-3">
            <AllowanceMeter used={USAGE.runsUsed} limit={USAGE.runsLimit} />
          </div>
        </section>

        <section className="panel px-5 py-4">
          <h2 className="text-[14px] font-semibold">Model requests today</h2>
          <p className="mt-1 font-display text-[28px] tnum">
            {USAGE.callsUsed}
            <span className="text-[16px] text-ink-muted"> of {USAGE.callsLimit}</span>
          </p>
          <p className="mt-3 text-[13px] text-ink-muted">
            Only unfamiliar columns cost a request. Most migrations use one or
            two; a migration never uses more than three.
          </p>
        </section>
      </div>

      <section className="panel mt-4 px-5 py-4">
        <h2 className="text-[14px] font-semibold">Your account</h2>
        <dl className="mt-3 space-y-2 text-[13.5px]">
          <div className="flex gap-3">
            <dt className="w-28 shrink-0 text-ink-muted">Signed in as</dt>
            <dd>{ACCOUNT.email}</dd>
          </div>
          <div className="flex gap-3">
            <dt className="w-28 shrink-0 text-ink-muted">Sign-in</dt>
            <dd>Google</dd>
          </div>
          <div className="flex gap-3">
            <dt className="w-28 shrink-0 text-ink-muted">Resets</dt>
            <dd>12:00 AM IST daily</dd>
          </div>
        </dl>
      </section>

      <section className="panel mt-4 px-5 py-4">
        <h2 className="text-[14px] font-semibold">What is stored</h2>
        <p className="mt-2 max-w-[62ch] text-[13.5px] text-ink-muted">
          The files you upload, the records built from them and the decisions you
          made are kept for 48 hours so you can reopen a migration, then deleted.
          Use synthetic data only — do not upload real personal information.
        </p>
      </section>
    </div>
  );
}
