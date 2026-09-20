# Auth0 Google sign-in setup

SchemaBridge uses one Auth0 Single-Page Application and one RS256 API. The
browser receives only public SPA configuration; the API verifies access tokens
and derives the workspace owner server-side.

## Auth0 resources

Create these in the Auth0 tenant:

1. **Application:** `SchemaBridge Web`, type **Single Page Web Application**.
   - Enable Authorization Code with PKCE and refresh-token rotation.
   - Authorise it for the SchemaBridge API permissions
     `migrations:read` and `migrations:write`.
2. **API:** `SchemaBridge API`, identifier `https://api.schemabridge.app`, signed
   with **RS256**.

For every application origin, configure three distinct Auth0 allow-list entries:

| Setting | Local development | Production/preview pattern |
| --- | --- | --- |
| Allowed Callback URLs | `http://localhost:3000/app` | `https://your-origin/app` |
| Allowed Logout URLs | `http://localhost:3000` | `https://your-origin` |
| Allowed Web Origins | `http://localhost:3000` | `https://your-origin` |

The frontend redirects to `${origin}/app` after sign-in, so registering only the
origin as a callback URL is incorrect. Each preview URL needs its own entries
unless the Auth0 tenant policy permits a safe wildcard for that deployment domain.

## Google-only Universal Login

In the Auth0 Dashboard:

1. Configure the **Google / Google OAuth2** social connection.
2. Enable it for **SchemaBridge Web** only.
3. Disable database, passwordless, and other connections for this application.
4. Do not configure an organization requirement or a hosted-domain restriction if
   any valid Google account should be able to create an account at first login.

The frontend passes `connection=google-oauth2`, which deliberately bypasses a
connection picker. Consumer Gmail and Google Workspace accounts can both sign in.
A Workspace administrator may independently block third-party OAuth applications;
that Google-side policy cannot be bypassed by SchemaBridge.

### Production Google credentials

Auth0 permits testing a Google connection with shared developer keys, but Auth0
documents that setup as non-production. It produces an Auth0-branded consent
screen and has limitations around custom domains, SSO/session checks, federated
logout, MFA, and redirect Actions. For a deployed application, create a Google
Cloud OAuth client owned by the project and place its client id and secret in the
Auth0 Google connection. This is an Auth0/Google configuration change; the
SchemaBridge frontend already uses the correct connection name.

## Environment boundary

Server-only root `.env.local` values validate access tokens:

```dotenv
AUTH0_ISSUER=https://YOUR_TENANT_REGION.auth0.com
AUTH0_AUDIENCE=https://api.schemabridge.app
AUTH0_JWKS_CACHE_SECONDS=3600
```

Public frontend values belong in `frontend/.env.local` locally, or in the
frontend deployment environment:

```dotenv
NEXT_PUBLIC_AUTH0_DOMAIN=YOUR_TENANT_REGION.auth0.com
NEXT_PUBLIC_AUTH0_CLIENT_ID=YOUR_SPA_CLIENT_ID
NEXT_PUBLIC_AUTH0_AUDIENCE=https://api.schemabridge.app
```

Never expose an Auth0 application secret, Management API token, MongoDB URI,
inference key, Langfuse secret, or `OBSERVABILITY_API_SECRET` through a
`NEXT_PUBLIC_*` variable.

## Build-time behaviour

Next.js replaces these public values while creating the browser bundle:

- `NEXT_PUBLIC_AUTH0_DOMAIN`
- `NEXT_PUBLIC_AUTH0_CLIENT_ID`
- `NEXT_PUBLIC_AUTH0_AUDIENCE`

Adding or changing them after a deployment build leaves that deployment with its
old bundle. Set the values before deployment, then redeploy. If sign-in appears
inert, inspect the browser console and confirm the deployed frontend was built
with all three values.

## Workspace behaviour

A valid access token is verified using the Auth0 issuer, audience, RS256
signature, expiry, and rotating JWKS. The API hashes the verified issuer and
subject into an opaque personal workspace id. The browser cannot choose it.

No bearer token intentionally selects one shared anonymous workspace. Invalid or
expired supplied tokens receive a 401 rather than guest access. The personal and
shared workspace policies, quotas, and retention are documented in
[Operations](operations.md).
