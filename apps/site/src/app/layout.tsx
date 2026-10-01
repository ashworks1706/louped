import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { Provider } from "@/components/provider";
import { appName, tagline } from "@/lib/shared";
import "./global.css";

export const metadata: Metadata = {
  title: { default: `${appName}: ${tagline}`, template: `%s · ${appName}` },
  description:
    "An open-source, local testbed for research on language model behavior and efficiency: each question an experiment, measured and explained on the same model.",
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
