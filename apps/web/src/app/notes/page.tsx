import type { Metadata } from "next";
import { Suspense } from "react";

import { NotesView } from "@/components/notes-view";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Notes" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/notes/")} />
      <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-8">
        <Suspense>
          <NotesView />
        </Suspense>
      </div>
    </>
  );
}
