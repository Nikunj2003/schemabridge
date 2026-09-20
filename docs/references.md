# References and service notes

This document separates services and libraries used by the running application
from research and design influences. An influence is not a claim that its code or
method is deployed.

## Runtime services and primary documentation

| Component | Role in SchemaBridge | Reference |
| --- | --- | --- |
| Next.js | Browser workbench and application routing | <https://nextjs.org/docs> |
| FastAPI | Python API service and OpenAPI surface | <https://fastapi.tiangolo.com/> |
| Auth0 | Google-backed SPA authentication and RS256 JWT verification | <https://auth0.com/docs> |
| MongoDB | Checkpoints, run projections, quotas, receipts, and model evidence | <https://www.mongodb.com/docs/> |
| LangGraph | Durable state graph, interrupts, and checkpoint integration | <https://langchain-ai.github.io/langgraph/> |
| NVIDIA API | Configurable OpenAI-compatible inference endpoint | <https://build.nvidia.com/> |
| Langfuse | Optional, disabled-by-default telemetry export | <https://langfuse.com/docs> |
| JSON Schema | Target contract validation/import support | <https://json-schema.org/> |

Current package versions are pinned in `frontend/package.json` and
`backend/pyproject.toml`. `THIRD_PARTY_NOTICES.md` records direct dependency
licence categories; lockfiles and package metadata remain the source of truth
for the fully resolved dependency trees.

## Model configuration

The application accepts an OpenAI-compatible model endpoint through
`NVIDIA_BASE_URL` and `NVIDIA_MODEL`. The runtime fallback currently names
`nvidia/nemotron-3.5-lightning-30b-a3b`; `.env.example` demonstrates
`openai/gpt-oss-20b`. Model availability, terms, and output behaviour are
provider-dependent, so the migration engine verifies structured proposals and
keeps a human escalation path rather than treating a provider choice as a
correctness guarantee.

Consult the provider's current model licence and API terms before enabling a
model in an environment that handles data beyond the synthetic prototype.

## Design influences

The workbench prioritises visible evidence, focused review, and clear provenance
rather than confidence scores. Its visual tokens are adapted from the author's
own `codenex-ui` project as documented in `THIRD_PARTY_NOTICES.md`. The system's
specific workflow, rule policy, data model, and diagrams are original to this
repository.

## Operational references

- [Architecture](architecture.md) explains request, data, and trust boundaries.
- [Operations](operations.md) describes configuration, deployment, capacity, and
  operator-only observability.
- [Schemas and rules](schema-and-rules.md) explains contract ownership and
  incremental rule learning.
- [Auth0 and Google setup](auth0-google.md) documents the browser/server
  configuration boundary.
