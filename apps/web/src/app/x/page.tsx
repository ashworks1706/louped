import type { Metadata } from "next";
import { Suspense } from "react";

import { PluginPage } from "@/components/plugin-page";

export const metadata: Metadata = { title: "Plugin" };

export default function Page() {
  return (
    <Suspense>
      <PluginPage />
    </Suspense>
  );
}
