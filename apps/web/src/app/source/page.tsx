import type { Metadata } from "next";
import { Suspense } from "react";

import { SourceView } from "@/components/source-view";

export const metadata: Metadata = { title: "Source" };

export default function Page() {
  return (
    <Suspense>
      <SourceView />
    </Suspense>
  );
}
