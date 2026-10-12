import type { Metadata } from "next";
import { Suspense } from "react";

import { FeedbackView } from "@/components/feedback-view";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Feedback" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/feedback/")} />
      <div className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-8">
        <Suspense>
          <FeedbackView />
        </Suspense>
      </div>
    </>
  );
}
