"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { SchemaBuilder } from "@/components/schema/builder";
import { api, type TargetSchema } from "@/lib/api";

/**
 * A new schema, optionally seeded from an existing one.
 *
 * `?from=<id>` copies that schema's fields into the draft. This is the whole of
 * "editable by copy": the built-in template is never edited in place, and a copy
 * of it is an ordinary schema with no special status.
 */
export function NewSchema() {
  const params = useSearchParams();
  const from = params.get("from");
  const [source, setSource] = useState<TargetSchema | null>(null);
  const [limits, setLimits] = useState(40);
  const [state, setState] = useState<"loading" | "ready" | "failed">(
    from ? "loading" : "ready",
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const listing = await api.schemas.list();
        if (!live) return;
        setLimits(listing.limits.max_fields);
        if (from) {
          setSource(await api.schemas.read(from));
          if (live) setState("ready");
        }
      } catch (caught) {
        if (!live) return;
        // Only fatal when there was a schema to copy: without one the builder
        // works fine, it just does not know the field cap yet.
        if (from) {
          setError(
            caught instanceof Error ? caught.message : "That schema could not be loaded.",
          );
          setState("failed");
        } else {
          setState("ready");
        }
      }
    })();
    return () => {
      live = false;
    };
  }, [from]);

  if (state === "loading") {
    return <p className="px-8 py-8 text-[13.5px] text-ink-muted">Loading…</p>;
  }
  if (state === "failed") {
    return (
      <p role="alert" className="mx-auto max-w-[56rem] px-4 py-8 sm:px-8">
        <span className="block rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem">
          {error}
        </span>
      </p>
    );
  }
  return <SchemaBuilder source={source} schemaId={null} maxFields={limits} />;
}
