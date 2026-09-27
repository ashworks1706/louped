import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { Playground } from "@/components/playground";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Playground" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/playground/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Playground />
      </section>
    </>
  );
}
