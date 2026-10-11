import type { Metadata } from "next";
import { Suspense } from "react";

import { HubView } from "@/components/hub-view";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Hub" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/hub/")} />
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        <Suspense>
          <HubView />
        </Suspense>
      </div>
    </>
  );
}
