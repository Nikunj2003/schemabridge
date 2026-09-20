# Design notes

## Who this is for

An implementation consultant, mid-migration, with a client waiting. They
understand the business data. They do not read schemas or debug mapping code.
Their job is to answer only the questions that need human judgement—and to be
able to explain afterwards what happened to every record.

That audience rules out two tempting directions. This is not a developer console:
no raw JSON, no confidence scores, and no inscrutable model rationale. It is also
not a wizard: a step-by-step flow implies every field needs confirming, which is
exactly the micromanagement the product avoids.

## The design thesis

**The screen makes autonomous work legible and human work small.**

Most of the interface is evidence of decisions already committed. What needs a
person is focused into a clear review action with enough source context to decide
safely. An empty review state is success, not an unfinished task.

## Current workbench flow

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ SchemaBridge   [New migration] [Schemas] [Rules]          Account / usage │
├──────────────────────────────────────────────────────────────────────────┤
│ Run: files + target contract                 phase tracker + actor counts │
│                                                                          │
│  Migration audit                                                     │
│  ✓ source profiled     ✓ rule applied     ◌ model-assisted proposal    │
│  ! waiting for review  ✓ delivery receipt                            │
│                                                                          │
│  Every record: canonical values, disposition, source and repair context │
├──────────────────────────────────────────────────────────────────────────┤
│ Focused review dialog, only when needed                                 │
│ “Date” could be Start date or End date                                  │
│ source evidence + options → select an answer → save decision            │
└──────────────────────────────────────────────────────────────────────────┘
```

Navigation separates starting a migration, managing schemas/rules, and reviewing
usage. Within a run, phase state and actor counters provide orientation while the
migration audit and **Every record** presentation retain the evidence. A review
dialog takes focus only when the graph has genuinely interrupted for a person;
scheduling progress is not presented as a human task.

## The actions are explicit

A reviewer can:

- select and save an evidence-backed option;
- correct a value or mapping when the source knowledge says the offered option is
  wrong;
- reject or exclude a value with a visible consequence; and
- later inspect or accept a proposed rule for future runs.

Saving is deliberate. There is no autosave for a half-written rule or partially
selected answer. Every committed action appears in the audit, and corrections
are reprocessed by the engine rather than accepted unverified.

## What replaces confidence scores

Never a percentage. A consultant cannot act on `0.87`.

Instead, the product names why it stopped in plain language, for example:

> Both readings are valid dates, so choosing wrong would silently misdate every
> record in this file.

The domain layer creates these reasons. The UI presents them alongside the source
column, affected records, and permitted options rather than hiding them behind a
score.

## Live without fake progress

The activity view consists of committed audit events, polled from durable state.
Each line corresponds to a real event with an actor, reason, and when relevant a
before/after value. No progress bar claims a guessed percentage of work.

When a run awaits review, the interface says so and stops. When more automatic
work remains, the runner advances bounded graph steps and the audit grows from
committed checkpoints. This makes a quiet review state interpretable rather than
an endless animation.

## Rules and schema scope

A rule is the durable form of a decision someone already made. The rules page
makes two things obvious: what has been learned and whether it applies to the
selected target contract.

Every rule belongs to exactly one schema. An unscoped rule would be cheaper to
create but impossible to reason about: a consultant could not tell which future
run it might change. A schema choice costs one explicit selection and protects
other contracts from a local convention.

Learned, hand-written, and shipped rules have distinct provenance. Shipped rules
are read-only; a person can turn one off for their workspace through an owned
override without changing anyone else's engine. A rule proposal names the source
run and decision that motivated it.

### Deliberate omissions

- **No rule that resolves an ambiguous column.** A broad ambiguous header must
  remain a review question rather than become a silent mass mapping.
- **No confidence score on a proposal.** Provenance, rationale, and previewable
  impact are actionable; a numeric confidence is not.
- **No hidden immediate learning.** A proposed rule is reviewed after the run,
  explicitly accepted, and used by a future run. The current run keeps its
  initial policy snapshot.
