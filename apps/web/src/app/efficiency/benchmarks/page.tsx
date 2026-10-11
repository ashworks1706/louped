import type { Metadata } from "next";
import { Suspense } from "react";

import { SpeedBenchmarks } from "@/components/benchmarks-view";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Benchmarks" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/efficiency/benchmarks/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Suspense>
          <SpeedBenchmarks />
        </Suspense>
      </section>
    </>
  );
}
