import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { RunsList } from "@/components/runs-list";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Training" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/behavior/training/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <RunsList kind="training" />
      </section>
    </>
  );
}
