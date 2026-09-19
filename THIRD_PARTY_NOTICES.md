# Third-party notices

SchemaBridge is released under the MIT License (see `LICENSE`).

## Adapted source

### codenex-ui — MIT, Copyright (c) 2026 Nikunj Khitha

The design tokens in `src/app/globals.css` (colour scales, typography pairing,
spacing and radius conventions) are adapted from the author's own `codenex-ui`
project. Layout proportions used in the workbench shell — a 224px sidebar, a
56px header, and a split working pane — follow the same conventions. No
application logic was copied.

## Direct dependencies

Runtime dependencies retain their own licences, including:

**Frontend**

| Package | Licence |
| --- | --- |
| `next`, `react`, `react-dom` | MIT |
| `clsx`, `tailwind-merge`, `next-themes`, `tailwindcss` | MIT |
| `lucide-react` | ISC (includes MIT-licensed Feather-derived icons) |

**Backend**

| Package | Licence |
| --- | --- |
| `fastapi`, `pydantic`, `pydantic-settings` | MIT |
| `langgraph`, `langgraph-checkpoint-mongodb`, `langchain-openai` | MIT |
| `pandas`, `numpy` | BSD-3-Clause |
| `openpyxl` | MIT |
| `jsonschema`, `httpx` | MIT / BSD-3-Clause |
| `pymongo` | Apache-2.0 |

Run `npx license-checker` in `frontend/` and `pip-licenses` in `backend/` for
the full resolved trees. Model weights accessed over the hosted API are covered
by their own model licence (NVIDIA Nemotron open model licence) and the
provider's API terms; see `docs/references.md`.
