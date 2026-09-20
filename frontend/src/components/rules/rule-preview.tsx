"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api, type RuleInput, type RulePreview } from "@/lib/api";

/**
 * What a draft would do, tried against a real file before it is saved.
 *
 * This exists because a rule is invisible in operation. It fires during a migration
 * and the only evidence is a row in the audit that a person may not read. Asking
 * someone to approve a rule they cannot try is asking them to trust a description,
 * so the page runs the draft through the real engine and reports what changed.
 *
 * The preview writes nothing — not the rule, not a run. The file is uploaded, parsed,
 * compared with and without the draft, and discarded.
 */
export function RulePreviewPanel({ draft, ready }: { draft: RuleInput; ready: boolean }) {
  const [result, setResult] = useState<RulePreview | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [running, setRunning] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const run = async (chosen: File[]) => {
    setRunning(true);
    setFailure(null);
    setResult(null);
    try {
      setResult(await api.rules.preview(draft, chosen));
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : "The preview could not run.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="panel mt-5 px-5 py-5 sm:px-6">
      <h2 className="text-[15px] font-semibold">Try it on a file</h2>
      <p className="mt-1 max-w-[62ch] text-[13px] text-ink-muted">
        Optional, and nothing is saved. Upload an export you already have and this
        shows exactly which columns and values the rule would touch.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        <label className="inline-flex h-9.5 cursor-pointer items-center rounded-md border border-line-strong bg-surface px-3.5 text-[13.5px] font-medium hover:bg-sunken">
          Choose files
          <input
            type="file"
            multiple
            accept=".csv,.txt,.xlsx"
            className="sr-only"
            onChange={(event) => {
              const chosen = Array.from(event.target.files ?? []);
              setFiles(chosen);
              if (chosen.length > 0 && ready) void run(chosen);
            }}
          />
        </label>
        {files.length > 0 && (
          <span className="text-[12.5px] text-ink-muted">
            {files.map((file) => file.name).join(", ")}
          </span>
        )}
        {files.length > 0 && (
          <Button
            size="sm"
            variant="secondary"
            disabled={!ready || running}
            onClick={() => void run(files)}
          >
            {running ? "Checking…" : "Check again"}
          </Button>
        )}
      </div>

      {!ready && files.length > 0 && (
        <p
          role="status"
          className="mt-4 rounded-md border border-attention/30 bg-attention-soft px-4 py-2.5 text-[13px] text-attention"
        >
          Finish the rule above and the preview will run.
        </p>
      )}

      {failure && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem"
        >
          {failure}
        </p>
      )}

      {result && (
        <div className="mt-4 border-t border-line pt-4">
          {result.would_change === 0 ? (
            <p className="text-[13.5px]">
              This rule would change nothing in {files.length === 1 ? "this file" : "these files"}.
              That is worth knowing before saving it: either the header is spelled
              differently here, or the engine already handles it.
            </p>
          ) : (
            <>
              <p className="text-[13.5px] font-medium">
                {result.would_change} {result.would_change === 1 ? "change" : "changes"}
              </p>

              {result.matched_columns.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {result.matched_columns.map((match, index) => (
                    <li key={index} className="text-[13px] text-ink-muted">
                      <span className="raw text-ink">{match.header}</span> in {match.file_name} →{" "}
                      {match.target_field || "left out"}
                    </li>
                  ))}
                </ul>
              )}

              {result.matched_values.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {result.matched_values.slice(0, 12).map((match, index) => (
                    <li key={index} className="text-[13px] text-ink-muted">
                      {match.field_name}: <span className="raw">{match.before}</span> →{" "}
                      <span className="raw text-ink">{match.after}</span>
                    </li>
                  ))}
                  {result.matched_values.length > 12 && (
                    <li className="text-[12.5px] text-ink-subtle">
                      and {result.matched_values.length - 12} more
                    </li>
                  )}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
