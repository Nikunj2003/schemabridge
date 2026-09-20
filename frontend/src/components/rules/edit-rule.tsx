"use client";

import { useEffect, useState } from "react";
import { RuleBuilder } from "@/components/rules/rule-builder";
import { RulesBuilderSkeleton } from "@/components/ui/skeleton";
import { api, type RuleView, type TargetSchema } from "@/lib/api";

/** One saved rule, opened for editing alongside the schema it belongs to. */
export function EditRule({ ruleId }: { ruleId: string }) {
  const [rule, setRule] = useState<RuleView | null>(null);
  const [schemas, setSchemas] = useState<TargetSchema[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const [loadedRule, listing] = await Promise.all([
        api.rules.read(ruleId).catch(() => null),
        api.schemas.list().catch(() => null),
      ]);
      if (!live) return;
      if (loadedRule && listing) {
        setRule(loadedRule);
        setSchemas([listing.builtin, ...listing.schemas]);
      } else {
        setError("This rule could not be opened.");
      }
    })();
    return () => {
      live = false;
    };
  }, [ruleId]);

  if (error) {
    return (
      <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8">
        <p role="alert" className="rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem">
          {error}
        </p>
      </div>
    );
  }

  if (!rule || !schemas) return <RulesBuilderSkeleton />;
  return <RuleBuilder source={rule} ruleId={ruleId} schemas={schemas} />;
}
