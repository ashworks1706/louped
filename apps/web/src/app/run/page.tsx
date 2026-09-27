import type { Metadata } from "next";
import { Suspense } from "react";

import { RunView } from "@/components/run-view";

export const metadata: Metadata = { title: "Run" };

export default function Page() {
  return (
    <Suspense>
      <RunView />
    </Suspense>
  );
}
