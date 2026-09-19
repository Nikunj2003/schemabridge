"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ButtonLink } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

interface Row {
  run_id: string;
  created_at: string;
  files: string[];
  source_rows: number;
}

/** The runs this person owns, newest first. */
export function MigrationList() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listRuns()
      .then((result) => setRows(result.runs))
      .catch(() => setError("Your migrations could not be loaded."));
  }, []);

  return (
    <div className="mx-auto max-w-[52rem] px-4 py-6 sm:px-8 sm:py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[24px]">Your migrations</h1>
          <p className="mt-1.5 text-[14px] text-ink-muted">
            Pick up where you left off, or start a new one.
          </p>
        </div>
        <ButtonLink href="/app/new" variant="primary">
          New migration
        </ButtonLink>
      </div>

      {error && (
        <p role="alert" className="mt-6 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem">
          {error}
        </p>
      )}

      {rows === null && !error && <MigrationListSkeleton />}

      {rows !== null && rows.length === 0 && (
        <div className="panel mt-6 px-5 py-6">
          <h2 className="font-display text-[17px]">Nothing here yet</h2>
          <p className="mt-1.5 max-w-[56ch] text-[14px] text-ink-muted">
            Add two employee exports that do not quite agree with each other. The
            agent reconciles what it can and asks you about the rest.
          </p>
          <ButtonLink href="/app/new" variant="primary" className="mt-4">
            Start your first migration
          </ButtonLink>
          <p className="mt-4 text-[13px] text-ink-muted">
            Sample files ship with the project at{" "}
            <span className="raw">backend/fixtures/samples/</span>.
          </p>
        </div>
      )}

      {rows !== null && rows.length > 0 && (
        <ul className="mt-6 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface">
          {rows.map((row) => (
            <li key={row.run_id}>
              <Link
                href={`/app/migrations/${row.run_id}`}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 hover:bg-sunken"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-medium">{row.files.join(" · ")}</p>
                  <p className="mt-0.5 text-[12.5px] text-ink-muted tnum">
                    {row.source_rows} source rows · {when(row.created_at)}
                  </p>
                </div>
                <span className="text-[13px] font-medium text-accent">Open</span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-8 text-[12.5px] text-ink-muted">
        Migrations are kept for 48 hours, then deleted.
      </p>
    </div>
  );
}

function MigrationListSkeleton() {
  return (
    <div className="mt-6 overflow-hidden rounded-lg border border-line bg-surface" aria-busy="true">
      <span className="sr-only">Loading migrations…</span>
      {[0, 1, 2].map((index) => (
        <div key={index} className="flex items-center gap-4 border-b border-line px-5 py-4 last:border-b-0">
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-[min(22rem,78%)]" />
            <Skeleton className="h-3 w-28" />
          </div>
          <Skeleton className="h-4 w-10" />
        </div>
      ))}
    </div>
  );
}

function when(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  return at.toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
