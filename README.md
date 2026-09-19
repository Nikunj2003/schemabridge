# SchemaBridge

An AI-assisted data migration workbench. It ingests several inconsistent
exports of the same entity, works out how they map onto a target schema, safely
cleans what it can, and pushes validated records to a destination API —
pausing to ask a human only when a decision genuinely needs judgement.

> **Status:** working prototype on synthetic data. Not hardened for real
> employee records. See [Known limitations](#known-limitations).

## Why it exists

Migrations stall on the same problem: the source files disagree with each
other. Column names differ, dates arrive in three formats, the same person
appears twice with conflicting details, required values are missing.

Manual mapping tools make a human confirm every field, which does not scale.
Fully automatic tools guess silently, which is worse — a wrong guess on a start
date is invisible until payroll runs.

SchemaBridge takes the middle path: act where the evidence is unambiguous,
escalate a small well-explained queue where it is not.

## How it decides

Every mapping lands in one of three outcomes:

1. **Deterministic** — the header matches a known alias, values are
   type-compatible, no other column competes for the same target. Applied
   automatically.
2. **Model-assisted** — an unfamiliar header. A language model proposes
   candidates; a proposal is applied only if independent deterministic checks
   agree. Model confidence alone is never permission.
3. **Escalated** — two plausible targets, competing columns, a missing
   required field, or a transformation that would change meaning.

The model proposes. Application code decides. It cannot rewrite rows, invent
missing values, or reach the destination API.

Records are validated **exactly twice**: once as mapped, then once more after a
single bounded pass of safe repairs. A record failing both is escalated with
both error sets, rather than retried indefinitely.

## Architecture

One repository, one deployment, one URL.

```
Browser
   │
   ├── /            →  Next.js 16 + TypeScript      (workbench UI)
   └── /api/*       →  FastAPI + Python 3.12        (migration engine)
                          │
                          ├── ingestion      CSV + Excel, enforced limits
                          ├── profiling      pandas column statistics
                          ├── mapping policy explicit gates, no blended score
                          ├── cleanup        meaning-preserving repairs only
                          ├── identity       conservative reconciliation
                          ├── validation     two passes, then escalate
                          ├── LangGraph      checkpointed workflow + interrupts
                          └── mock target    protected stub over real HTTP
                                 │
              ┌──────────────────┴───────────────────┐
              ▼                                      ▼
      MongoDB Atlas                        NVIDIA-hosted model
   (checkpoints, projection,              (mapping proposals only)
    receipts, budgets)
```

### Durable human-in-the-loop

The workflow is a LangGraph `StateGraph` checkpointed to MongoDB. When the
agent reaches something ambiguous it calls `interrupt()`; the run pauses with
its state persisted. A later request resumes it with `Command(resume=decision)`.

This matters because the backend runs as serverless functions: each request is
a different process, so in-memory state would lose every paused run. The
checkpointer is what makes "pause for a human" survive that. Graph position
lives only in the checkpointer — the application's own collections hold the
reviewer-facing projection, delivery receipts, sessions and usage budgets.

## Tech stack

| Layer | Choice |
| --- | --- |
| UI | Next.js 16 (App Router), React 19, TypeScript, Tailwind v4 |
| API | FastAPI, Python 3.12, Pydantic |
| Orchestration | LangGraph with the MongoDB checkpointer |
| Model | Open-weights, via an OpenAI-compatible endpoint (see below) |
| Data | pandas (profiling), openpyxl (Excel), jsonschema (target contract) |
| Database | MongoDB Atlas |
| Tests | pytest, ruff, mypy (strict) |

### On the model

Set `NVIDIA_MODEL` to any OpenAI-compatible open-weights model. Two are tested:

| Model | Licence | Measured |
| --- | --- | --- |
| `openai/gpt-oss-20b` (default) | Apache-2.0 | ~2–11s for a schema-constrained reply |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | NVIDIA open model licence | 17s when idle, 75s when the free endpoint is busy |

Switching is a one-line change with no code edit, which matters more than it
sounds: free endpoints fluctuate hard. The same Nemotron endpoint answered a
bare ping in 17s one hour and 75s the next. The adapter sends the switches both
families use and sizes the output ceiling per family, so either works unchanged.

Three settings come from measurement rather than documentation:

- **Reasoning is minimised.** With it left on, schema-constrained requests
  exceeded 45s and returned nothing usable, having spent the whole token budget
  thinking. At low effort the same request answers in about 11s.
- **Output headroom is generous.** A reasoning model emits its thinking first, so
  at 300 tokens gpt-oss returned *only* reasoning and no answer at all.
- **Structured output is pinned** to `json_schema` with `strict=True`. Of the
  four available strategies, the default took twice as long, `json_mode` timed
  out, and `function_calling` returned a null target *without raising* — which
  would have written nulls into mappings instead of failing visibly.

If the endpoint is slow or unavailable, the run does not fail: deterministic
mappings still apply, and the columns the model was meant to help with stay in
the review queue with the reason shown. A visible gap beats a confident guess.

## Setup

Requires **Python 3.12+**, **Node 24**, and a MongoDB Atlas cluster.

```bash
cp .env.example .env.local        # then fill in the values

# backend
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
./.venv/bin/uvicorn main:app --reload --port 8000

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

`.env.example` documents every variable. All secrets are server-side and never
reach the browser.

Verify external services before running the app:

```bash
cd backend
./.venv/bin/python -m schemabridge.smoke.mongo    # Atlas connectivity
./.venv/bin/python -m schemabridge.smoke.nvidia   # model access and latency
```

## Commands

| Command | Purpose |
| --- | --- |
| `cd backend && ./.venv/bin/pytest -q` | Tests (no network needed) |
| `cd backend && ./.venv/bin/ruff check .` | Lint |
| `cd backend && ./.venv/bin/mypy schemabridge main.py` | Types (strict) |
| `cd frontend && npm run lint` | Lint the UI |
| `cd frontend && npm run typecheck` | Types |
| `cd frontend && npm run build` | Production build |

## Known limitations

- **Synthetic data only.** No real personal data should be uploaded.
- **Bounded inputs.** Small file, row and column limits are enforced
  server-side to stay within free-tier capacity.
- **Progress needs an open tab.** State is durable and resumes on reload, but
  the browser drives each processing step; there is no background worker.
- **Delivery is at-least-once with idempotent effects.** A request whose
  response is lost is retried under the same idempotency key, so the
  destination cannot create a duplicate. This is not exactly-once.
- **Shared inference budget.** The public demo caps model requests, so heavy
  traffic can temporarily exhaust capacity.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — design and data flow
- [`docs/approach.md`](docs/approach.md) — the autonomy boundary, in one page
- [`docs/demo-guide.md`](docs/demo-guide.md) — walkthrough
- [`docs/references.md`](docs/references.md) — prior art consulted

## Licence

MIT — see [`LICENSE`](LICENSE) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Built with the help of AI coding tools.
