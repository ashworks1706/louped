import { Move3d } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Vectors" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/vectors/")} phase={3} />
      <section className="mx-auto max-w-5xl px-6 py-8">
        <EmptyState
          icon={Move3d}
          title="No vectors saved"
          body="Directions computed from activations, with the runs that produced and used them."
          command="loupe vectors diff-in-means --help"
        />
      </section>
    </>
  );
}
