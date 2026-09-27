import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { AppSidebar } from "@/components/app-sidebar";
import { CommandMenu } from "@/components/command-menu";
import { Providers } from "@/components/providers";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "loupe", template: "%s · loupe" },
  description: "A research testbed for looking inside language models.",
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
              <div className="flex min-h-dvh flex-col md:flex-row">
                <AppSidebar />
                <main className="min-w-0 flex-1">{children}</main>
              </div>
            </CommandMenu>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
