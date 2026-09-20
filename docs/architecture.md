# Architecture

SchemaBridge is a two-service application deployed behind one origin: a Next.js
workbench at `/` and a FastAPI migration service at `/api/*`. It is designed to
make evidence, authority, and retention explicit rather than treating an LLM call
as the workflow.

For a visual companion with current diagrams, read the
[hosted architecture report](https://nikunj.codenex.dev/artifacts/schemabridge/schemabridge-architecture.html).

## System boundaries

```text
Browser (Next.js)
  │ Auth0 SPA SDK: Google sign-in, token restore, explicit guest choice
  ▼
FastAPI API
  ├─ Auth0 JWT/JWKS verification → private workspace principal
  ├─ no bearer token             → intentionally shared guest principal
  ├─ API routes                  → run, schema, rule, sample, and usage views
  └─ operator-secret route       → cross-workspace observability only
  │
  ├─ MongoDB Atlas
  │    ├─ LangGraph checkpoints (authoritative run evidence)
  │    ├─ manifests, schemas/rules, receipts, quotas
  │    ├─ model exchanges and global rate reservations
  │    └─ TTL expiry indexes
  ├─ OpenAI-compatible model endpoint
  ├─ optional Langfuse telemetry (off by default)
  └─ destination HTTP API / demo target
```

The browser never submits an owner identifier. `auth.py` derives an opaque,
pseudonymous `owner_id` from a verified Auth0 issuer and subject. No token means
one fixed `anonymous:shared` workspace by design. A malformed bearer token is a
401, never an anonymous fallback.

## Workspace policy and retention

| Principal | Data visibility | Daily starts | Retention |
| --- | --- | ---: | ---: |
| Authenticated | Only the verified subject's workspace | 20, India calendar day | 168 hours |
| Anonymous | One deliberately shared workspace | 100 total, India calendar day | 48 hours |

The start route reserves quota atomically in MongoDB before it creates a run.
A run receives one immutable `run_expires_at`, carried into its manifest,
checkpoints, delivery receipts, and model exchanges. The run registry filters
expired manifests before MongoDB's asynchronous TTL monitor physically removes
them.

Checkpoint databases are separated by workspace kind. The custom saver stores
`expires_at`, not a sliding `created_at` deadline, and retains a bounded recent
checkpoint history. This prevents a frequently reviewed migration from extending
its retention indefinitely.

## The migration workflow

1. **Ingest and profile.** CSV and Excel sources are parsed under size, row, and
   column limits. The run state preserves source rows, column profiles, and the
   target schema snapshot.
2. **Map.** Known aliases and deterministic policies handle unambiguous columns.
   Unresolved headers may get a structured model proposal. Deterministic
   verification validates the proposal before it can become a mapping.
3. **Reconcile and normalise.** Records merge only on conservative identity
   evidence. Cleanup normalises only safe forms; ambiguous dates, unknown enum
   semantics, and unsafe edits remain visible.
4. **Validate and interrupt.** A first validation succeeds immediately or gets
   one safe repair/revalidation cycle. Genuine uncertainty calls LangGraph
   `interrupt()` with review options and evidence.
5. **Resume and deliver.** A reviewer submits decisions. The runner resumes from
   the durable checkpoint, then sends records over HTTP with bounded retries and
   stable idempotency keys.
6. **Propose learning.** After delivery, a reviewed decision or verified mapping
   can yield a proposed schema-scoped rule. Explicit acceptance saves it for
   future runs; it cannot alter the snapshotted rule set of the current run.

The runner intentionally advances a small number of graph supersteps per
request. This keeps a serverless request bounded and makes polling show committed
progress. Closing a browser tab stops scheduling but does not lose state.

## State, projections, and audit

The LangGraph checkpoint is the authoritative, detailed run record. It includes
source rows, canonical records shown under **Every record**, mappings, issues,
review decisions, delivery attempts, proposed rules, and append-only audit
events. The application does not duplicate that large state into a separate
record collection.

Smaller Mongo collections provide lifecycle and operational projections:

- run manifests locate a checkpoint and enforce ownership/expiry;
- schemas and rules are owned by the workspace but snapshotted into each run;
- delivery receipts protect target effects across retries;
- migration quota documents enforce the selected policy atomically;
- model exchanges preserve each logical model call for an operator; and
- model-rate documents coordinate all serverless instances using the shared
  inference key.

Audit events mark whether the **system**, a **rule**, the **model**, or the
**reviewer** performed an action. Rule-driven events include the rule identity
and origin, so an avoided model request is explainable rather than invisible.

## Model, rate limit, and telemetry

The model has two deliberately narrow jobs: proposing mappings for unresolved
columns and drafting a reusable rule from an approved decision. Both jobs use a
centralised invocation boundary. It persists a pending `model_exchanges` entry
before the outbound call, records completion or error afterwards, and shares the
run expiry.

Before each physical provider attempt, MongoDB reserves a globally spaced slot.
At the default 45 requests per minute this is one provider start every 4/3
seconds across instances. Transient failures retry with bounded backoff and a
new reservation; transport retries do not consume another logical per-run model
allowance.

Langfuse is optional. `LANGFUSE_ENABLED=false` is the default. When it is
configured, exports use run correlation and pseudonymous ownership; telemetry
failure must not fail a migration. Content capture is separately explicit.

## External APIs and authority

Normal run, schema, and rule routes operate only in the requesting workspace.
`/api/observability/*` is deliberately different: it requires the separate
server-only `x-schemabridge-operator-secret`, compared in constant time. Auth0
end-user tokens do not grant cross-workspace observability.

`/api/health` reports configuration booleans and selected model metadata without
credentials. It is useful for diagnosing deployment configuration, but it does
not claim a live probe of every dependency.

## Guarantees and deliberate non-goals

SchemaBridge guarantees durable review state, bounded processing, clear actor
provenance, explicit workspace separation, and idempotent destination effects
when the target honours the supplied key. It does **not** claim exactly-once
network transport, a compensating rollback API, semantic proof of a
model-assisted mapping, background processing while all tabs are closed, or
production readiness for real personal data.
