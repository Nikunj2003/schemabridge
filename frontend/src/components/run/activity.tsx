import { Dot, type Tone } from "@/components/ui/status";
import type { ActivityLine } from "@/lib/sample";

/**
 * What has been done so far, newest last.
 *
 * Grouped by useful fact — "Combined 2 duplicate rows" — rather than one line per
 * cell. The per-value detail lives behind the change history.
 */
export function Activity({ lines, live }: { lines: ActivityLine[]; live: boolean }) {
  return (
    <section>
      <div className="flex items-center gap-2">
        <h2 className="text-[15px] font-semibold">Already handled</h2>
        {live && (
          <span className="flex items-center gap-1.5 text-[12.5px] text-accent">
            <Dot tone="working" busy />
            still working
          </span>
        )}
      </div>

      <ol className="mt-3 space-y-3">
        {lines.map((line) => (
          <li key={line.id} className="flex gap-3">
            <span className="mt-[7px]">
              <Dot tone={line.tone as Tone} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[14px] leading-snug">{line.text}</p>
              {line.detail && (
                <p className="mt-0.5 text-[13px] leading-snug text-ink-muted">{line.detail}</p>
              )}
            </div>
            <time className="raw shrink-0 text-[12px] text-ink-subtle">{line.at}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}
