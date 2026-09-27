import type { Metadata } from "next";
import { Suspense } from "react";

import { CompareView } from "@/components/compare-view";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Compare" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/compare/")} />
      <Suspense>
        <CompareView />
      </Suspense>
    </>
  );
}
