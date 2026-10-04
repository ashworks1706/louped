import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { Provider } from "@/components/provider";
import { appName, tagline } from "@/lib/shared";
import "./global.css";

export const metadata: Metadata = {
  title: { default: `${appName}: ${tagline}`, template: `%s · ${appName}` },
  description:
    "A local workbench for research on LLM behavior and efficiency. Your coding agent runs the experiments; you read the results.",
};

export default function Layout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} ${GeistSans.className} antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-screen flex-col">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
