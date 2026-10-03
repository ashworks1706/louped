import type { Metadata } from "next";

import { DomainOverview } from "@/components/domain-overview";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Efficiency" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/efficiency/")} title="Efficiency" />
      <DomainOverview section="efficiency" />
    </>
  );
}
