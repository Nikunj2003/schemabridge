# Trying it out

## Sample files

All four are invented, in `backend/fixtures/samples/`. Each exists to force a
particular decision.

| File | What it exercises |
| --- | --- |
| `employees-clean.csv` | Nothing. It should complete without asking you anything. |
| `employees-legacy.csv` | Messy values, an ambiguous date, an unrepairable email, and two records the destination handles badly. |
| `employees-hr-export.csv` | Different header spellings, a duplicate that merges, a conflict that does not, and a column that could be two fields. |
| `employees-directory.xlsx` | Excel-typed dates and a header no alias table knows, so the model is asked. |

## The two runs worth seeing

### 1. Upload `employees-clean.csv` on its own

Expect: **no questions at all.** It maps six columns, validates three records,
delivers all three, and finishes. The review pane says "Nothing needs you".

This is the more important of the two. The brief asks for an agent that does not
micromanage, and a clean file is where that claim is either true or not.

### 2. Upload `employees-legacy.csv` **and** `employees-hr-export.csv` together

Expect **four questions**, and twelve columns mapped without asking:

| Question | Why the agent stopped |
| --- | --- |
| `Date` could be Start date or End date | Both readings are valid, and picking wrong would misdate every row in the file |
| E-1003 has two different start dates | Both sources assert a value and they disagree |
| E-1004 failed validation twice | `03/04/2026` has no safe reading — it could be 3 April or 4 March |
| E-1005 failed validation twice | `meera.joshi@@example..com` is not repairable by any safe rule |

Things worth looking for while resolving them:

- **Press `1` or `2`** instead of clicking. The queue counter drops immediately.
- **The reason text**, not a score. There is no percentage anywhere in the
  interface, deliberately.
- **Rahul Verma merged silently.** He is in both files with `full-time` in one and
  `Permanent` in the other. Those mean the same thing, so it is not a conflict —
  and E-1003, which genuinely disagrees, is.
- **`000123` keeps its leading zeros.** Check the Records tab.
- **E-1007 fails, then succeeds.** The Delivery tab shows a 503, a scheduled
  retry, and then acceptance.
- **E-1008 is rejected for good.** The destination refuses it on a business rule,
  which is a failure a person has to act on rather than something to retry.

Then read the **Audit** tab. Every line has an actor, a reason, and a
before/after where a value changed — including the decisions you just made,
attributed to you rather than to the agent.

## Running it

```bash
cp .env.example .env.local   # then fill in the values
./run.sh
```

Open http://localhost:3000. The script installs dependencies on first run.

You need:

- **Python 3.12+** and **Node 24**
- A **MongoDB Atlas** connection string in `MONGODB_URI`
- An **API key** for an OpenAI-compatible endpoint in `NVIDIA_API_KEY`

Without the model key everything still works except the one unknown header in
the Excel file, which becomes a question instead of being resolved
automatically. That is the intended degradation, not a failure.

## Checking the parts separately

```bash
cd backend
./.venv/bin/python -m schemabridge.smoke.mongo    # database reachable
./.venv/bin/python -m schemabridge.smoke.nvidia   # model reachable, and how fast

# A run paused in one process, finished by another — the durability claim
./.venv/bin/python -m schemabridge.smoke.resume --phase start  --thread demo
./.venv/bin/python -m schemabridge.smoke.resume --phase resume --thread demo

./.venv/bin/pytest -q                             # 183 tests
```
