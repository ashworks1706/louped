import type { Metadata } from "next";

import { DomainOverview } from "@/components/domain-overview";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Behavior" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/behavior/")} title="Behavior" />
      <DomainOverview section="behavior" />
    </>
  );
}
