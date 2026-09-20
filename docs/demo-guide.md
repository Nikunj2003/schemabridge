# Trying SchemaBridge

## Before you start

Use synthetic data only. Choose **Continue as guest** to explore the deliberately
shared guest workspace, or sign in with Google for a private workspace. Guest
runs, schemas, rules, and audit history are intentionally visible to every guest.

Start locally:

```bash
cp .env.example .env.local
./run.sh
```

Open <http://localhost:3000>. For model-assisted scenarios, configure an
OpenAI-compatible model key. Without it, deterministic work still runs and the
unknown column becomes an explicit review question instead of a model-assisted
mapping.

## Download the synthetic samples

In **New migration**, select **Demo files** (the information button). The dialog
lists downloadable files and the scenario each combination is designed to show.
The files are also present under `backend/fixtures/samples/` for local work.

| File | What it exercises |
| --- | --- |
| `employees-clean.csv` | An unambiguous clean path without review or model use. |
| `employees-legacy.csv` | Messy values, ambiguous date handling, an unrepairable email, and destination failures. |
| `employees-hr-export.csv` | Different header spellings, safe duplicate merge, genuine conflict, and competing-column ambiguity. |
| `employees-directory.xlsx` | Typed Excel dates plus an unknown header that can use one model request. |

Sample outcomes assume the built-in schema and no previously approved rule that
already changes the scenario. Upload order does not matter: files are read
together. Uploading one source twice does not create duplicate people when the
identity evidence permits a merge.

## Three useful walkthroughs

### 1. A clean file, start to finish

Upload `employees-clean.csv` on its own.

Expect a run that maps, validates, and delivers all records without a review
stop. Watch the counters and the inline migration audit: rules and deterministic
policy do the work, and no model request is needed. Open **Every record** to see
the delivered canonical rows.

### 2. Two exports that disagree

Upload `employees-legacy.csv` and `employees-hr-export.csv` together.

The engine resolves compatible aliases and safe duplicates automatically, then
pauses for genuine judgement. Typical evidence includes:

- `Date` matching more than one target date field;
- the same person carrying conflicting source values;
- a numeric date with two plausible interpretations; and
- a record that remains invalid after one safe repair attempt.

Use the focused review dialog. Read the reason and evidence, select the safest
option (or correct/exclude it), then **save** the decision. The workflow resumes
from its durable checkpoint and revalidates corrections. The audit records your
choice separately from model, rule, and system actions.

Look for two intentional differences:

- compatible values such as equivalent employment-type spellings can merge
  without a question, while conflicting values do not; and
- delivery can show a transient retry or a permanent target rejection. A stable
  idempotency key protects the target from duplicate effects across retry.

### 3. Model assistance that becomes reusable policy

Upload `employees-directory.xlsx` on its own.

Most headers resolve by existing policy. `Cost Centre Ref` is intentionally
unknown, so the model receives one structured mapping request. When the provider
is available, deterministic verification can accept the proposal and the run can
finish without a blocking question. The audit and counters show the model's role.

After delivery, inspect **Worth remembering**. The run can offer a schema-scoped
mapping rule with its evidence. Accepting it stores a rule for a **future** run;
it does not change the completed run's snapshot. Upload the workbook again to
see that the rule can avoid the repeated model request.

## A value-learning example

Create a small CSV with an unrecognised employment type:

```csv
emp_id,emp_nm,email,doj,dept,emp_type
T-1,Ana Roy,ana@example.com,2026-01-05,Sales,Seasonal Temp
T-2,Bo Lin,bo@example.com,2026-02-05,Sales,Seasonal Temp
```

The run escalates because the engine will not invent the business meaning of
`Seasonal Temp`. Resolve it as the appropriate canonical value, review the
proposed value-alias rule after delivery, and accept it only if the
generalisation is sound for this schema. A later run can then handle the
spelling deterministically.

## Rules worth testing

Try to create a header rule mapping `Date` to a particular target date field
when the schema has multiple plausible date targets. The API refuses it: a
reusable rule must not erase an ambiguity that could silently misdate every row.

Use rule preview before saving a manual rule. It reports matching columns/values
and how many records would change, but it does not bypass the same validation
used for learned rules.

## Checkpoint durability demonstration

With MongoDB configured, the following demonstrates that one process can persist
a paused run and another can resume it:

```bash
cd backend
./.venv/bin/python -m schemabridge.smoke.resume --phase start --thread demo
./.venv/bin/python -m schemabridge.smoke.resume --phase resume --thread demo
```

Run the quality suite through the commands in the [README](../README.md#commands).
Report the actual command output for your revision rather than relying on a
historic test count.
