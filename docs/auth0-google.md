# Auth0 Google sign-in setup

SchemaBridge uses one Auth0 Single-Page Application and one RS256 API.

## Auth0 resources

Create these in the Auth0 tenant:

1. **Application:** `SchemaBridge Web`, type **Single Page Web Application**.
   - Enable Authorization Code with PKCE and refresh-token rotation.
   - Add each deployment origin exactly to Allowed Callback URLs, Allowed Logout URLs, and Allowed Web Origins. For local development use `http://localhost:3000`.
2. **API:** `SchemaBridge API`, identifier `https://api.schemabridge.app`, signed with **RS256**.
   - Add `migrations:read` and `migrations:write` permissions.
   - Authorize `SchemaBridge Web` for both permissions.

The browser receives only the Auth0 domain, SPA client id, and API audience. Do not place an Auth0 Management API token or an application secret in browser configuration.

## Google-only Universal Login

The Auth0 MCP API cannot configure the Google connection because Google OAuth client credentials are required. In Auth0 Dashboard:

1. Create or configure the **Google / Google OAuth2** social connection with a Google Cloud OAuth client id and secret.
2. Enable that connection for **SchemaBridge Web** only.
3. Disable database, passwordless, and other connections for this application.
4. Do not add an organization requirement or a Google Workspace domain restriction; this allows any valid Google account to create an Auth0 account at first login.

The frontend deliberately sends `connection=google-oauth2`, so it bypasses a connection picker and cannot select a non-Google option.

## Environment

Server-only (`.env.local`):

```dotenv
AUTH0_ISSUER=https://YOUR_TENANT_REGION.auth0.com
AUTH0_AUDIENCE=https://api.schemabridge.app
```

Frontend deployment environment:

```dotenv
NEXT_PUBLIC_AUTH0_DOMAIN=YOUR_TENANT_REGION.auth0.com
NEXT_PUBLIC_AUTH0_CLIENT_ID=YOUR_SPA_CLIENT_ID
NEXT_PUBLIC_AUTH0_AUDIENCE=https://api.schemabridge.app
```

Set production callback/logout/web origins before deploying to that production origin. Never set a `NEXT_PUBLIC_` value for `OBSERVABILITY_API_SECRET`, Langfuse secrets, NVIDIA keys, Mongo URI, or Auth0 server credentials.
