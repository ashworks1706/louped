import type { Metadata } from "next";
import { Suspense } from "react";

import { ExperimentsList } from "@/components/experiments-list";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Experiments" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/experiments/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Suspense fallback={<Skeleton className="h-10 w-full" />}>
          <ExperimentsList />
        </Suspense>
      </section>
    </>
  );
}
