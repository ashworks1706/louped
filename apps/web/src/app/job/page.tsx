import type { Metadata } from "next";
import { Suspense } from "react";

import { JobView } from "@/components/jobs";

export const metadata: Metadata = { title: "Job" };

export default function Page() {
  return (
    <Suspense>
      <JobView />
    </Suspense>
  );
}
