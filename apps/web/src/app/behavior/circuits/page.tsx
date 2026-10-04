import type { Metadata } from "next";
import { Suspense } from "react";

import { CircuitsView } from "@/components/circuits-view";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Circuits" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/behavior/circuits/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Suspense>
          <CircuitsView />
        </Suspense>
      </section>
    </>
  );
}
