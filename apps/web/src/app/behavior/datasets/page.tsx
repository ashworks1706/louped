import type { Metadata } from "next";
import { Suspense } from "react";

import { DatasetsView } from "@/components/datasets-view";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Datasets" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/behavior/datasets/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Suspense>
          <DatasetsView domain="behavior" />
        </Suspense>
      </section>
    </>
  );
}
