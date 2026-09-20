# SchemaBridge approach

## The approach

SchemaBridge turns inconsistent CSV and Excel exports into records for a declared
target schema through an explicit workflow: ingest and profile the files; map
headers; reconcile records that can be safely identified as the same person;
apply meaning-preserving cleanup; validate; deliver accepted records; and retain
the audit trail. The goal is not to make every decision automatic. It is to make
the safe path fast and the uncertain path visible.

A clean export can move from mapping to delivery without a review stop. A messy
export pauses with evidence such as a competing header, conflicting identity
value, ambiguous date, or record that remains invalid after one bounded repair
attempt. The reviewer can approve, correct, reject, or exclude. Corrections are
put back through the workflow and validated again.

## What the agent handles—and what it escalates

The agent works autonomously only when it has an explainable basis:

- a shipped or previously approved schema-scoped rule matches without contention;
- a deterministic policy can reconcile or clean a value without changing its
  meaning; or
- a model proposes an unfamiliar mapping and independent code accepts the
  proposal after checking the target, occupancy, and value-kind compatibility.

It escalates whenever the data admits more than one materially plausible reading,
a required value is not safely supplied, or a transformation would invent or
change business meaning. The model is never an execution authority: it cannot
write rows, bypass validation, or call the target API. Provider failure also
fails safely—deterministic work remains, and the unresolved item is shown to the
reviewer.

## Engineering beyond a model call

The workflow is designed around dependable decisions rather than a one-shot
prompt. MongoDB-backed LangGraph checkpoints preserve a paused review across
serverless requests. The audit distinguishes system, rule, model-assisted, and
reviewer actions. Delivery is real HTTP with bounded retry and stable idempotency
keys, giving at-least-once transport with idempotent target effects rather than
claiming exactly once. Inputs, repair attempts, model requests, and provider
throughput are bounded.

Every model exchange is retained with run correlation, attempts, timing, and an
expiry shared with the run. A global Mongo-coordinated 45-RPM gate prevents
separate serverless instances from overspending the shared provider allowance.
Optional Langfuse export is disabled by default and fail-open when enabled.

## Incremental learning and token discipline

A reviewed decision or verified model mapping may produce a proposed rule. The
reviewer must explicitly keep it. The resulting rule is scoped to one schema,
records its provenance, can be previewed, and passes the same validation whether
it was drafted by the model or written manually. Runs snapshot their schema and
rules at creation, so a newly approved rule improves future matching without
changing a run that is already underway or delivered.

This is deliberately selective LLM use. Known headers, valid aliases, and
repeated decisions are solved by deterministic policy and approved rules; the
model is called only for genuine semantic uncertainty or to draft a reusable
rule. That reduces token use while making each remaining call traceable and
worth reviewing.

## What comes next

The prototype should gain background execution independent of an open browser,
production data controls, real destination connectors, larger-workload handling,
and systematic evaluation of model-assisted mapping quality. These improvements
would strengthen operational scale and safety without changing the central
principle: automate evidence-backed work, expose judgement calls, and learn only
from explicitly approved decisions.
