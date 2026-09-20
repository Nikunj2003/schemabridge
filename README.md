# SchemaBridge

SchemaBridge is an AI-assisted workbench for reconciling inconsistent data exports
into a declared target schema. It ingests several CSV or Excel files, preserves
what each source said, applies only meaning-preserving transformations, and sends
validated records to a destination API. It asks a reviewer only when the evidence
does not support a safe decision.

> **Prototype boundary:** SchemaBridge uses synthetic data and is not hardened for
> real personal data. Read [limitations](#known-limitations) before operating it.

## Why it exists

Exports that describe the same people rarely agree. Headers vary, dates use
multiple conventions, values conflict, and required fields may be missing.
Confirming every value manually is slow; silently guessing is unsafe. SchemaBridge
uses a narrower contract instead: automate an answer only when it is supported by
explicit policy, then make uncertainty visible and actionable.

## How it decides

Every source column reaches one of four outcomes:

1. **Rule-applied** — a shipped or approved, schema-scoped rule matches without a
   competing target. The mapping is applied deterministically.
2. **Model-assisted** — an unfamiliar header is sent to the model for a structured
   proposal. Application code independently checks the target, occupancy, and
   value-kind compatibility before accepting it. Model confidence is never
   permission to write.
3. **Escalated** — a plausible ambiguity, identity conflict, missing required
   value, invalid record, or meaning-changing cleanup becomes a plain-language
   question for a reviewer.
4. **Excluded** — an explicit rule or reviewer decision says the value should not
   enter the target record.

The model proposes; policy code decides. The model cannot directly rewrite rows,
invent missing values, or call the destination API.

Records that validate on their first evaluation continue immediately. A failing
record gets **one bounded automatic safe-repair pass** and a re-evaluation. If it
still fails, the reviewer sees the error evidence rather than an unbounded retry
loop. A later human correction is reprocessed and validated; it is not trusted
just because a person entered it.

## Learning without broadening trust

An approved answer can become a reusable rule, not a hidden prompt-memory effect.
SchemaBridge drafts a rule from a reviewed decision or a verified model mapping;
the reviewer can inspect its provenance and keep or decline it. A saved rule is:

- **schema-scoped**, so one contract's vocabulary cannot change another's run;
- **data, not executable code**, using normalised equality rather than a custom
  predicate;
- **previewable** before it is saved;
- **validated through the same checks** whether it was written by a person or
  proposed by the model; and
- effective on **future runs**. A migration's schema and active rule set are
  snapshotted when it starts, so an answer cannot silently change half of an
  already-delivered run.

This is also the token strategy. Known headers and prior approved decisions do not
need a model call. The model is reserved for genuine semantic uncertainty and
rule drafting, so each request has a specific job and the audit can show both
model requests made and requests avoided.

## Architecture at a glance

```text
Browser: Next.js + React
  │  Google sign-in or deliberately shared guest workspace
  ▼
/api/*: FastAPI migration service
  ├─ ingest + profile → deterministic mapping/rules → verified model proposal
  ├─ reconcile → safe cleanup → validation → explicit human interruption
  ├─ bounded, idempotent HTTP delivery → post-delivery rule proposal
  └─ durable audit events for system, rule, model, and reviewer actions
  │
  ├─ MongoDB Atlas: checkpoints, run manifests, schemas/rules, receipts,
  │                quotas, model exchanges, and rate reservations
  ├─ NVIDIA-compatible model endpoint: globally spaced at 45 RPM with retry
  └─ optional Langfuse: disabled by default and fail-open when enabled
```

The detailed data flow, trust boundaries, retention design, and diagrams are in
[the architecture guide](docs/architecture.md). Its shareable visual companion
is published at **[SchemaBridge architecture report](https://nikunj.codenex.dev/artifacts/schemabridge/schemabridge-architecture.html)**.

### Durable human review

The migration workflow is a MongoDB-checkpointed LangGraph state machine. When
it reaches a genuine judgement call, it interrupts with evidence and persists
its exact graph state. A later request can apply approve, correct, reject, or
exclude decisions and resume safely—even if it lands in a different serverless
process. Browser requests deliberately advance only a bounded number of steps;
closing the tab pauses scheduling, not the persisted run.

## Workspaces, limits, and retention

| Workspace | Visibility | Daily migration starts | Retention |
| --- | --- | ---: | ---: |
| Google-backed personal workspace | Isolated to the verified Auth0 subject | 20 per India calendar day | 168 hours |
| Shared anonymous workspace | Intentionally visible to every guest | 100 total per India calendar day | 48 hours |

A missing access token selects the shared guest workspace intentionally. A
supplied token is always verified against Auth0's issuer, audience, signature,
and rotating JWKS; an invalid token is rejected rather than falling back to the
guest workspace.

Input limits are enforced server-side: up to three files, 2 MiB combined, 500
rows per file, 1,000 rows total, and 50 columns. Migration-start limits are
separate from the shared model budget and the provider's 45-RPM request gate.

## Tech stack

| Layer | Choice |
| --- | --- |
| UI | Next.js 16, React 19, TypeScript, Tailwind CSS |
| API | FastAPI, Python 3.12, Pydantic |
| Workflow | LangGraph with MongoDB checkpointing and interrupts |
| Data | pandas, openpyxl, JSON Schema, YAML |
| Identity | Auth0 SPA + RS256 API access tokens; Google-only login |
| Persistence | MongoDB Atlas |
| Model | OpenAI-compatible, open-weights endpoint |
| Telemetry | Durable model-exchange evidence; optional Langfuse export |
| Quality | pytest, Ruff, strict mypy, frontend lint/typecheck/build |

### Model boundary

`NVIDIA_MODEL` is configurable. The code fallback is
`nvidia/nemotron-3.5-lightning-30b-a3b`; `.env.example` demonstrates
`openai/gpt-oss-20b` as an alternative. Schema-constrained output is requested
from the provider, then treated as untrusted input by deterministic verification.

Each logical model exchange is recorded with its run, operation, attempts,
latency, sanitised request/response information, and the same expiry as its run.
A Mongo-coordinated gate spaces provider starts globally at 45 RPM. Transient
provider failures retry within a bounded request window without double-charging
the logical model budget. Langfuse is off by default; when deliberately enabled,
telemetry failures do not fail a migration.

## Local setup

Requires **Python 3.12+**, **Node 24**, and a MongoDB Atlas connection.

```bash
cp .env.example .env.local
./run.sh
```

`run.sh` prepares the backend and frontend dependencies on first use, then starts
both services. Open <http://localhost:3000>.

Configure server-only values in the root `.env.local`. Configure the three public
Auth0 values in `frontend/.env.local` before starting or building the frontend:

```dotenv
NEXT_PUBLIC_AUTH0_DOMAIN=YOUR_TENANT_REGION.auth0.com
NEXT_PUBLIC_AUTH0_CLIENT_ID=YOUR_SPA_CLIENT_ID
NEXT_PUBLIC_AUTH0_AUDIENCE=https://api.schemabridge.app
```

`NEXT_PUBLIC_*` values are embedded at frontend build time. Setting them after a
deployment is built does not change the browser bundle; redeploy after changing
them. See [Auth0 and Google setup](docs/auth0-google.md) for callback URLs and
safe configuration boundaries.

## Commands

| Command | Purpose |
| --- | --- |
| `cd backend && ./.venv/bin/pytest -q` | Run backend tests |
| `cd backend && ./.venv/bin/ruff check .` | Lint Python |
| `cd backend && ./.venv/bin/ruff format --check .` | Check Python formatting |
| `cd backend && ./.venv/bin/mypy schemabridge main.py` | Run strict type checks |
| `cd frontend && npm run lint` | Lint the UI |
| `cd frontend && npm run typecheck` | Type-check the UI |
| `cd frontend && npm run build` | Build the production UI |

For a cross-process checkpoint demonstration, use the documented two-phase
commands in [the demo guide](docs/demo-guide.md) against a configured local
MongoDB instance.

## API surfaces

- [`/api/health`](/api/health) reports configuration state without exposing
  credentials. It is not a live dependency probe.
- [`/api/docs`](/api/docs) provides the interactive API documentation.
- [`/api/openapi.json`](/api/openapi.json) provides the OpenAPI document.
- `/api/observability/*` is intentionally separate: it requires the server-only
  operator secret, not an end-user Auth0 token.

## Known limitations

- **Synthetic-data prototype.** Do not upload real personal data.
- **Browser-driven scheduling.** State survives a reload, but no background
  worker advances a run while every browser tab is closed.
- **At-least-once delivery.** The destination sees a stable idempotency key, so a
  lost response can be retried without duplicate effects; this is not exactly-once
  transport and there is no compensating rollback endpoint.
- **Bounded capacity.** Uploads, per-run model requests, daily model use, and
  shared provider throughput are capped for a demo environment.
- **Model verification is not semantic proof.** Deterministic gates reject
  structurally unsafe proposals, but ambiguous business meaning still belongs to
  a reviewer.

## Documentation

- [Architecture](docs/architecture.md) — data flow, persistence, trust boundaries, and retention
- [Approach brief](docs/approach.md) — one-page autonomy and engineering summary
- [Operations](docs/operations.md) — configuration, deployment, limits, and observability
- [Schemas and rules](docs/schema-and-rules.md) — contracts, imports, previews, and provenance
- [Demo guide](docs/demo-guide.md) — sample files and a current walkthrough
- [Design notes](docs/design-notes.md) — interaction principles
- [Auth0 and Google setup](docs/auth0-google.md) — sign-in configuration
- [References](docs/references.md) — runtime services and research/design sources
- [Detailed architecture report](https://nikunj.codenex.dev/artifacts/schemabridge/schemabridge-architecture.html) — visual system, workflow, retention, and model-control diagrams
- [Hosted approach brief](https://nikunj.codenex.dev/artifacts/schemabridge/schemabridge-approach-brief.html) — one-page overview of the approach and decision boundary

## Licence

MIT — see [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
