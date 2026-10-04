import type { Metadata } from "next";
import { Suspense } from "react";

import { ExperimentView } from "@/components/experiment-view";

export const metadata: Metadata = { title: "Experiment" };

export default function Page() {
  return (
    <Suspense>
      <ExperimentView axis="behavior" />
    </Suspense>
  );
}
