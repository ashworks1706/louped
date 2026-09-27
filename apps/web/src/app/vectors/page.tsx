import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";
import { VectorsTable } from "@/components/vectors-table";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Vectors" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/vectors/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <VectorsTable />
      </section>
    </>
  );
}
