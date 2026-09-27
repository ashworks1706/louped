import { GitCompareArrows } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Compare" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/compare/")} phase={2} />
      <section className="mx-auto max-w-5xl px-6 py-8">
        <EmptyState
          icon={GitCompareArrows}
          title="Pick two runs to compare"
          body="Metrics, flipped samples and transcript diffs, aligned by sample id."
          command="open Runs, select two rows, press C"
        />
      </section>
    </>
  );
}
