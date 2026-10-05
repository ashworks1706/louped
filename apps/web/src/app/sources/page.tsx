import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { SourcesView } from "@/components/sources-view";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Sources" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/sources/")} />
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-8">
        <Suspense>
          <SourcesView />
        </Suspense>
      </div>
    </>
  );
}
