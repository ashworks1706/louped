import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { TrainingSets } from "@/components/training-sets";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Training sets" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/behavior/training-sets/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Suspense>
          <TrainingSets />
        </Suspense>
      </section>
    </>
  );
}
