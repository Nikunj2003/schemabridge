# Third-party notices

SchemaBridge is released under the MIT License (see `LICENSE`).

## Adapted source

### codenex-ui — MIT, Copyright (c) 2026 Nikunj Khitha

The design tokens in `frontend/src/app/globals.css`—colour scales, typography
pairing, spacing, and radius conventions—are adapted from the author's own
`codenex-ui` project. No application logic was copied.

## Direct dependencies

Runtime dependencies retain their own licences. Package manifests and lockfiles
are authoritative for exact versions and resolved transitive dependencies.

**Frontend**

| Package group | Licence |
| --- | --- |
| `next`, `react`, `react-dom`, `@auth0/auth0-react` | MIT |
| `clsx`, `tailwind-merge`, `next-themes`, `tailwindcss` | MIT |
| `lucide-react` | ISC (includes MIT-licensed Feather-derived icons) |

**Backend**

| Package group | Licence |
| --- | --- |
| `fastapi`, `pydantic`, `pydantic-settings` | MIT |
| `langgraph`, `langgraph-checkpoint-mongodb`, `langchain-openai` | MIT |
| `pandas`, `numpy` | BSD-3-Clause |
| `openpyxl`, `PyYAML` | MIT |
| `jsonschema`, `httpx` | MIT / BSD-3-Clause |
| `pymongo`, `PyJWT` | Apache-2.0 / MIT |
| `langfuse` | MIT |

Run `npx license-checker` in `frontend/` and `pip-licenses` in `backend/` for
full resolved trees. Model weights accessed over a hosted API have their own
licences and provider terms. Service and model configuration notes are in
[docs/references.md](docs/references.md); consult the current provider terms
before enabling a model for data beyond this synthetic prototype.
