import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { Playground, PROBE } from "@/components/playground";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Probe" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/behavior/probe/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Playground tools={PROBE} />
      </section>
    </>
  );
}
