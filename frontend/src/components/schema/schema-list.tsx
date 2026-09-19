"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/status";
import { Button, ButtonLink } from "@/components/ui/button";
import { api, type SchemaListing, type TargetSchema } from "@/lib/api";
import { KIND_LABEL } from "@/lib/schema";

/**
 * The schemas this account can migrate onto.
 *
 * The built-in template is listed first and marked read-only, because the honest
 * answer to "can I change this?" is "not in place — copy it". Presenting it as an
 * editable row and then refusing the save would be worse.
 */
export function SchemaList() {
  const [listing, setListing] = useState<SchemaListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const loaded = await api.schemas.list();
      setListing(loaded);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Saved schemas could not be loaded.");
    }
  }, []);

  useEffect(() => {
    // Awaited rather than called synchronously, so the state lands in a later
    // tick than the effect body — the lint rule's actual concern.
    let live = true;
    void (async () => {
      const loaded = await api.schemas.list().catch(() => null);
      if (!live) return;
      if (loaded) setListing(loaded);
      else setError("Saved schemas could not be loaded.");
    })();
    return () => {
      live = false;
    };
  }, []);

  const remove = async (schemaId: string) => {
    setRemoving(schemaId);
    try {
      await api.schemas.remove(schemaId);
      setConfirming(null);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The schema could not be deleted.");
    } finally {
      setRemoving(null);
    }
  };

  return (
    <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8 sm:py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-[24px]">My schemas</h1>
          <p className="mt-1.5 max-w-[60ch] text-[14px] text-ink-muted">
            A schema is what the destination expects. Each migration maps onto one,
            so a different client can have a different shape. Upload one as a JSON
            or YAML spec, or build it field by field.
          </p>
        </div>
        <ButtonLink href="/app/schema/new" variant="primary">
          New schema
        </ButtonLink>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-5 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem"
        >
          {error}
        </p>
      )}

      {listing === null && !error && (
        <p className="mt-6 text-[13.5px] text-ink-muted">Loading…</p>
      )}

      {listing && (
        <>
          <section className="mt-7">
            <h2 className="eyebrow">Built in</h2>
            <SchemaCard schema={listing.builtin} className="mt-2.5" />
          </section>

          <section className="mt-7">
            <h2 className="eyebrow">Yours</h2>
            {listing.schemas.length === 0 ? (
              <div className="panel mt-2.5 px-5 py-8 text-center">
                <p className="text-[14px] font-medium">No schemas of your own yet</p>
                <p className="mx-auto mt-1 max-w-[46ch] text-[13px] text-ink-muted">
                  Copy the built-in one and change what differs, or build a new
                  shape from scratch.
                </p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  <ButtonLink href={`/app/schema/new?from=${listing.builtin.schema_id}`} size="sm">
                    Copy the built-in one
                  </ButtonLink>
                  <ButtonLink href="/app/schema/new" size="sm" variant="quiet">
                    Upload a spec or build one
                  </ButtonLink>
                </div>
              </div>
            ) : (
              <ul className="mt-2.5 space-y-2.5">
                {listing.schemas.map((schema) => (
                  <li key={schema.schema_id}>
                    <SchemaCard
                      schema={schema}
                      confirming={confirming === schema.schema_id}
                      removing={removing === schema.schema_id}
                      onAskRemove={() => setConfirming(schema.schema_id)}
                      onCancelRemove={() => setConfirming(null)}
                      onRemove={() => void remove(schema.schema_id)}
                    />
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-[12.5px] text-ink-subtle tnum">
              {listing.schemas.length} of {listing.limits.max_schemas} saved
            </p>
          </section>
        </>
      )}
    </div>
  );
}

function SchemaCard({
  schema,
  className,
  confirming,
  removing,
  onAskRemove,
  onCancelRemove,
  onRemove,
}: {
  schema: TargetSchema;
  className?: string;
  confirming?: boolean;
  removing?: boolean;
  onAskRemove?: () => void;
  onCancelRemove?: () => void;
  onRemove?: () => void;
}) {
  const required = schema.fields.filter((field) => field.required);
  const identity = schema.fields.find((field) => field.is_identity);

  return (
    <div className={className}>
      <div className="panel px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[15px] font-semibold">{schema.name}</h3>
              {schema.builtin ? (
                <Badge>Read-only</Badge>
              ) : (
                <span className="text-[12px] text-ink-subtle tnum">v{schema.version}</span>
              )}
            </div>
            {schema.description && (
              <p className="mt-1 max-w-[62ch] text-[13px] text-ink-muted">{schema.description}</p>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap gap-2">
            <a
              href={api.schemas.specUrl(schema.schema_id)}
              download
              className="inline-flex h-8 shrink-0 items-center rounded-md px-2.5 text-[13px] font-medium text-ink-muted hover:bg-sunken hover:text-ink"
              title="Download as a YAML spec"
            >
              Export
            </a>
            {schema.builtin ? (
              <ButtonLink href={`/app/schema/new?from=${schema.schema_id}`} size="sm">
                Copy and edit
              </ButtonLink>
            ) : (
              <>
                <ButtonLink href={`/app/schema/${schema.schema_id}`} size="sm">
                  Edit
                </ButtonLink>
                {onAskRemove && (
                  <Button size="sm" variant="quiet" onClick={onAskRemove}>
                    Delete
                  </Button>
                )}
              </>
            )}
          </div>
        </div>

        <dl className="mt-3.5 flex flex-wrap gap-x-6 gap-y-1.5 text-[12.5px]">
          <div className="flex gap-1.5">
            <dt className="text-ink-subtle">Fields</dt>
            <dd className="tnum">{schema.fields.length}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-ink-subtle">Required</dt>
            <dd className="tnum">{required.length}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-ink-subtle">Identified by</dt>
            <dd>{identity ? identity.label : "nothing — rows never merge"}</dd>
          </div>
        </dl>

        <ul className="mt-3 flex flex-wrap gap-1.5">
          {schema.fields.slice(0, 8).map((field) => (
            <li
              key={field.name}
              className="rounded border border-line bg-sunken px-2 py-1 text-[11.5px] text-ink-muted"
              title={`${field.label} — ${KIND_LABEL[field.kind]}`}
            >
              {field.label}
              {field.required && <span className="ml-1 text-accent-ink">*</span>}
            </li>
          ))}
          {schema.fields.length > 8 && (
            <li className="px-1.5 py-1 text-[11.5px] text-ink-subtle">
              +{schema.fields.length - 8} more
            </li>
          )}
        </ul>
      </div>

      {confirming && (
        <div className="mt-2 rounded-md border border-problem/30 bg-problem-soft px-4 py-3">
          <p className="text-[13px] text-problem">
            Delete {schema.name}? Migrations that already used it keep their own
            copy, so their history is unaffected.
          </p>
          <div className="mt-2.5 flex gap-2">
            <Button size="sm" variant="danger" disabled={removing} onClick={onRemove}>
              {removing ? "Deleting…" : "Delete it"}
            </Button>
            <Button size="sm" variant="quiet" onClick={onCancelRemove}>
              Keep it
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
