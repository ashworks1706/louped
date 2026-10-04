import type { Metadata } from "next";
import { Suspense } from "react";

import { FeatureView } from "@/components/feature-view";

export const metadata: Metadata = { title: "Feature" };

export default function Page() {
  return (
    <Suspense>
      <FeatureView />
    </Suspense>
  );
}
