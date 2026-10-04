import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { CommandMenu } from "@/components/command-menu";
import { Providers } from "@/components/providers";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "louped", template: "%s · louped" },
  description: "A local testbed for research on LLM behavior and efficiency.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} antialiased`}
      suppressHydrationWarning
    >
      <body>
        <ThemeProvider>
          <Providers>
            <CommandMenu>
              <AppShell>{children}</AppShell>
            </CommandMenu>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
