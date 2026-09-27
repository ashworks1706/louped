"use client";

import { ThemeProvider as NextThemes } from "next-themes";
import * as React from "react";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemes attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      {children}
    </NextThemes>
  );
}
