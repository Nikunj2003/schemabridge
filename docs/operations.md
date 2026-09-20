# Operations guide

## Deployment shape

`vercel.json` deploys the frontend as the `web` service and FastAPI as the `api`
service. Rewrites keep both behind one origin:

- `/api/*` reaches FastAPI;
- all other routes reach Next.js.

The same-origin setup lets the browser use relative API paths while the backend
uses a server-side target origin for outbound delivery when required.

## Configuration boundary

Copy `.env.example` to the root `.env.local` for server-only configuration. It
contains MongoDB, target, inference, retention, quota, Auth0 verification,
operator-observability, and optional Langfuse settings. Never place those
secrets in a `NEXT_PUBLIC_*` variable.

The frontend has a separate build-time configuration file:

```dotenv
# frontend/.env.local
NEXT_PUBLIC_AUTH0_DOMAIN=YOUR_TENANT_REGION.auth0.com
NEXT_PUBLIC_AUTH0_CLIENT_ID=YOUR_SPA_CLIENT_ID
NEXT_PUBLIC_AUTH0_AUDIENCE=https://api.schemabridge.app
```

Next.js inlines `NEXT_PUBLIC_*` values into the browser bundle during the build.
Set them in the hosting platform **before** deployment and redeploy whenever
they change. Do not put Mongo, inference, operator, Langfuse-secret, or Auth0
server credentials in the browser bundle.

## Auth0 and Google configuration

For each origin, configure distinct Auth0 entries:

| Auth0 setting | Local example | Production pattern |
| --- | --- | --- |
| Allowed Callback URL | `http://localhost:3000/app` | `https://your-origin/app` |
| Allowed Logout URL | `http://localhost:3000` | `https://your-origin` |
| Allowed Web Origin | `http://localhost:3000` | `https://your-origin` |

The frontend requests `connection=google-oauth2`, so the login action is
Google-only. A Google Workspace user can sign in just like a consumer Google
user unless their Workspace administrator blocks the OAuth application.

For a durable deployment, configure the Auth0 Google connection with the
project's own verified Google OAuth client. Auth0 shared developer keys are
suitable for testing but have production limitations such as an Auth0-branded
consent screen and impaired SSO-related features. See
[Auth0 and Google setup](auth0-google.md).

## Capacity policy

| Control | Default | Scope |
| --- | ---: | --- |
| Authenticated migration starts | 20/day | One verified workspace, India calendar day |
| Anonymous migration starts | 100/day | One shared guest workspace, India calendar day |
| Authenticated retention | 168 hours | Per run and related artifacts |
| Anonymous retention | 48 hours | Per run and related artifacts |
| Model requests per run | 6 | Logical model calls |
| Model requests per day | 400 | Shared demo budget |
| Provider rate | 45 RPM | Globally spaced across instances |
| Files per run | 3 | Server-enforced |
| Combined upload size | 2 MiB | Server-enforced |
| Rows | 500/file; 1,000 total | Server-enforced |
| Columns | 50 | Server-enforced |

Quotas reserve a run start atomically. A client that crosses midnight during a
failed creation releases the reservation associated with the original calendar
day, not a recalculated day. Provider rate spacing and retries are separate from
migration-start quotas.

## Health, API docs, and observability

- `GET /api/health` returns version plus configuration state without secrets.
  It does not contact each dependency, so `status: ok` is not a full live-service
  check.
- `GET /api/docs` provides the Swagger UI.
- `GET /api/openapi.json` provides the contract for tooling.
- `/api/observability/status`, `/runs`, and `/runs/{id}` require
  `x-schemabridge-operator-secret`. This operator secret is separate from
  end-user Auth0 access tokens and should be held only by authorised operators.

Each logical inference exchange is stored even when Langfuse is disabled. Set
`LANGFUSE_ENABLED=true` only with `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` configured. `LANGFUSE_CAPTURE_CONTENT=false` remains the
safe default. The telemetry adapter is fail-open, so a telemetry outage should
not stop a migration.

## Local workflow

```bash
cp .env.example .env.local
./run.sh
```

For direct development instead of `run.sh`:

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/uvicorn main:app --reload --port 8000

# separate terminal
cd frontend
npm install
npm run dev
```

Run the quality suite before deployment:

```bash
cd backend
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy schemabridge main.py
./.venv/bin/pytest -q

cd ../frontend
npm run lint
npm run typecheck
npm run build
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Google sign-in button is disabled or guest mode is selected | Check build-time `NEXT_PUBLIC_AUTH0_*` values and redeploy after changing them. |
| Google login returns to the wrong page | Confirm callback URL is exactly `<origin>/app`; logout and web-origin values remain `<origin>`. |
| A guest sees other guest migrations | Expected: guest mode is intentionally one shared workspace. Sign in with Google for isolation. |
| A signed-in user sees no expected private migrations | Confirm the same Auth0 tenant/issuer and subject are used; invalid tokens reject rather than becoming guest data. |
| A model step waits or declines | Check the shared daily budget, 45-RPM queue, model configuration, and audit reason. Deterministic work should still progress. |
| A run stops when the tab closes | State is retained; reopening it lets browser-driven advancement continue. A background worker is not implemented. |
