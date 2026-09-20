"use client";

import { useEffect, useState } from "react";
import { RuleBuilder } from "@/components/rules/rule-builder";
import { RulesBuilderSkeleton } from "@/components/ui/skeleton";
import { api, type TargetSchema } from "@/lib/api";

/**
 * A blank rule, once the schemas it can belong to have loaded.
 *
 * Every schema is fetched, not just the built-in one, because a rule belongs to
 * exactly one contract and that choice has to be a real choice. Waiting is better
 * than rendering a form that would silently attach the rule to the wrong schema.
 */
export function NewRule() {
  const [schemas, setSchemas] = useState<TargetSchema[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const listing = await api.schemas.list().catch(() => null);
      if (!live) return;
      if (listing) setSchemas([listing.builtin, ...listing.schemas]);
      else setError("Schemas could not be loaded, so a rule cannot be attached to one.");
    })();
    return () => {
      live = false;
    };
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8">
        <p role="alert" className="rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem">
          {error}
        </p>
      </div>
    );
  }

  if (!schemas) return <RulesBuilderSkeleton />;
  return <RuleBuilder source={null} ruleId={null} schemas={schemas} />;
}
