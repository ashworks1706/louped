import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportView } from "@/components/report-view";

export const metadata: Metadata = { title: "Report" };

export default function Page() {
  return (
    <Suspense>
      <ReportView />
    </Suspense>
  );
}
