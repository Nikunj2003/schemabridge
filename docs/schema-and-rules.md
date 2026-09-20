# Schemas and rules

SchemaBridge maps every run onto a target contract. The built-in contract is a
useful starting point, but a workspace can create its own schemas and rules
without altering another workspace's data.

## Target schemas

A target schema describes fields, labels, semantic kinds, requiredness, identity
and uniqueness constraints, enum values/aliases, and date-order relationships.
The UI supports a schema builder and a file/text import flow. Schema import reads
JSON or YAML specifications and surfaces assumptions that a generic schema format
cannot express—for example, which field identifies a person—rather than applying
them silently.

Schemas can be exported as YAML specifications. Saving and updating use versions,
so a stale editor cannot overwrite a concurrent change unnoticed.

At run creation, SchemaBridge snapshots the selected schema into the migration
state. Editing a schema later therefore does not change the contract used by an
in-progress or historical run.

## Rule layers

A run composes two layers:

1. **Built-in rules** derive from the target contract and are shared code-defined
   defaults.
2. **Owned rules** belong to the current workspace and one schema. They may be
   hand-written, learned from approved evidence, or overrides that disable a
   built-in rule for that workspace.

The engine recomposes the built-in layer with the run's owned snapshot when a
checkpoint is revived. This preserves a stable engine for a paused run while
avoiding duplicate built-in rules from older checkpoint formats.

## Rule kinds and provenance

Rules cover constrained decisions such as header aliases, value aliases, date
order, ignored columns, and overrides. They carry a stable id, kind, origin,
enabled state, schema id, rationale, hit count, and—when learned—provenance for
the run, issue, and decision that prompted it.

A rule is data rather than executable code. It cannot introduce an arbitrary
predicate or regular expression. This makes it possible to validate and preview
what it would do before saving.

Built-in rules are read-only. Turning one off creates an owned override; it does
not change the engine for every workspace.

## Guardrails

Rules cannot settle every question. In particular, a header that plausibly maps
to two target fields must remain an escalation; encoding one choice as a reusable
rule would make a broad, silent mistake possible. Manual rule creation and
model-proposed rules use the same validation path.

A model proposal can suggest a rule only after the mapping or reviewer decision
has already passed the workflow's safeguards. The reviewer still explicitly
accepts or declines the proposal. Rules accepted after delivery help a later run;
they do not retroactively re-run an already delivered migration.

## Preview, review, and operation

Before saving a draft, the rules UI sends the candidate rule together with the
currently selected files to the preview endpoint. The response names matching
columns/values and reports how many records would change. Treat this as an
impact preview, not permission to bypass the validation rules.

The Rules page lists shipped and owned layers separately. Scope the list to a
schema when evaluating whether a rule can affect the migration you are about to
start. Keep rationale concrete: name the source spelling, canonical target, and
business meaning that justified the decision.

## A practical learning loop

1. Run an unfamiliar export against a schema.
2. Resolve only the question that actually needs judgement.
3. Review the proposed rule and its provenance once the run has finished.
4. Preview and accept it only if the generalisation is safe for that schema.
5. Start a later migration with the same convention; the approved rule can avoid
   both the repeated question and the model request.

This creates incremental improvement without hidden fine-tuning or global
cross-customer memory.
