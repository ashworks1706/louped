import type { Metadata } from "next";
import { Suspense } from "react";

import { Launch } from "@/components/launch";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Launch" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/launch/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <Suspense>
          <Launch />
        </Suspense>
      </section>
    </>
  );
}
