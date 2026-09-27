import { FlaskConical } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Experiments" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/experiments/")} phase={2} />
      <section className="mx-auto max-w-5xl px-6 py-8">
        <EmptyState
          icon={FlaskConical}
          title="No experiments yet"
          body="Each folder under experiments/ becomes a card here, with its question and the runs that answer it."
          command="just new-experiment sycophancy-under-pressure"
        />
      </section>
    </>
  );
}
