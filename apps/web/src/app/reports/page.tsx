import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { ReportsView } from "@/components/reports-view";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Reports" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/reports/")} />
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-8">
        <Suspense>
          <ReportsView />
        </Suspense>
      </div>
    </>
  );
}
