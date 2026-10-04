import type { Metadata } from "next";

import { JobsPanel } from "@/components/jobs";
import { PageHeader } from "@/components/page-header";
import { RunsList } from "@/components/runs-list";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Runs" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/runs/")} />
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-8">
        <JobsPanel />
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium">Runs</h2>
          <RunsList />
        </section>
      </div>
    </>
  );
}
