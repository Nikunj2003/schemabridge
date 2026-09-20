"use client";

import { type AppState, Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { configureAccessTokenProvider } from "@/lib/api";

/**
 * Which workspace the browser is acting as.
 *
 * `authenticated` is a private, Google-backed workspace. `anonymous` is one
 * workspace shared by every guest, so its migrations, schemas, rules and audit
 * are deliberately visible to all of them.
 */
type WorkspaceMode = "anonymous" | "authenticated";

type WorkspaceContextValue = {
  mode: WorkspaceMode;
  /** Whether this deployment has Auth0's public settings, so sign-in can work. */
  configured: boolean;
  isLoading: boolean;
  displayName: string;
  signInWithGoogle: () => Promise<void>;
  signOut: () => void;
  switchToSharedWorkspace: () => void;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

const domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN;
const clientId = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID;
const audience = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE;

const GUEST_LABEL = "Shared anonymous workspace";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  // Without the public settings there is nothing to sign in against, so the app
  // runs as a guest rather than showing a button that cannot work.
  if (!domain || !clientId || !audience) {
    return <GuestWorkspaceProvider>{children}</GuestWorkspaceProvider>;
  }
  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        audience,
        scope: "openid profile email migrations:read migrations:write",
        redirect_uri: typeof window === "undefined" ? undefined : window.location.origin,
      }}
      useRefreshTokens
      // Persisted, so a reload or a returning visit does not silently drop the
      // session — with `memory` the person appeared signed out after any refresh.
      // The stored refresh token is rotating and therefore single-use, which is
      // what makes this an acceptable trade for a token in browser storage.
      cacheLocation="localstorage"
      onRedirectCallback={(state?: AppState) => {
        // A real navigation, not `history.replaceState`. Rewriting the address
        // bar alone left the router on the previous route, so signing in showed
        // the sign-in page under an /app URL.
        window.location.replace(returnTarget(state?.returnTo));
      }}
    >
      <ConfiguredWorkspaceProvider>{children}</ConfiguredWorkspaceProvider>
    </Auth0Provider>
  );
}

/** Where to land after Google returns.
 *
 * Only a same-origin path is honoured: `returnTo` survives a round trip through
 * the identity provider, so treating it as a URL would be an open redirect.
 * Signing in from the sign-in page itself has to go on to the app rather than
 * back to the page whose job is already done.
 */
function returnTarget(returnTo?: string): string {
  if (!returnTo || !returnTo.startsWith("/") || returnTo.startsWith("//")) return "/app";
  return returnTo === "/signin" || returnTo === "/" ? "/app" : returnTo;
}

function GuestWorkspaceProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    configureAccessTokenProvider(null);
    // These are inlined at build time, so a deployment built before they were
    // set has no way to sign anyone in. Saying so in the console turns a dead
    // button into a diagnosable one.
    if (process.env.NODE_ENV !== "test") {
      console.warn(
        "Auth0 is not configured in this build: NEXT_PUBLIC_AUTH0_DOMAIN, " +
          "NEXT_PUBLIC_AUTH0_CLIENT_ID and NEXT_PUBLIC_AUTH0_AUDIENCE must be " +
          "present at build time. Running in the shared guest workspace.",
      );
    }
  }, []);
  const value = useMemo<WorkspaceContextValue>(
    () => ({
      mode: "anonymous",
      configured: false,
      isLoading: false,
      displayName: GUEST_LABEL,
      signInWithGoogle: async () => undefined,
      signOut: () => undefined,
      switchToSharedWorkspace: () => undefined,
    }),
    [],
  );
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

function ConfiguredWorkspaceProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { isAuthenticated, isLoading, user, loginWithRedirect, logout, getAccessTokenSilently } =
    useAuth0();
  /**
   * Set when a signed-in person deliberately chooses the shared workspace.
   *
   * The mode is derived from this and Auth0's own state rather than mirrored into
   * state by an effect, so there is one source of truth for which workspace the
   * API client is speaking to.
   */
  const [preferGuest, setPreferGuest] = useState(false);
  const mode: WorkspaceMode = isAuthenticated && !preferGuest ? "authenticated" : "anonymous";

  useEffect(() => {
    // The API client attaches a bearer token only in personal mode; guest
    // requests deliberately carry none, which is what selects the shared
    // workspace server-side.
    configureAccessTokenProvider(
      mode === "authenticated" ? async () => getAccessTokenSilently() : null,
    );
    return () => configureAccessTokenProvider(null);
  }, [getAccessTokenSilently, mode]);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      mode,
      configured: true,
      isLoading,
      displayName:
        mode === "authenticated" && user
          ? user.name || user.email || "Signed-in workspace"
          : GUEST_LABEL,
      signInWithGoogle: async () => {
        setPreferGuest(false);
        await loginWithRedirect({
          // Where they were, unless that is the sign-in page itself.
          appState: { returnTo: returnTarget(pathname) },
          // Names the connection, so Universal Login goes straight to Google
          // rather than offering it among other options.
          authorizationParams: { connection: "google-oauth2" },
        });
      },
      signOut: () => {
        setPreferGuest(false);
        logout({ logoutParams: { returnTo: window.location.origin } });
      },
      switchToSharedWorkspace: () => setPreferGuest(true),
    }),
    [isLoading, loginWithRedirect, logout, mode, pathname, user],
  );
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider.");
  return value;
}
