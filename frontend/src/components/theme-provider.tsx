"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * SSR-safe theme provider. `next-themes` injects its script before hydration,
 * so no component reads `localStorage` during render.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
