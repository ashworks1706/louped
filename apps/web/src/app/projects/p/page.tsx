import type { Metadata } from "next";
import { Suspense } from "react";

import { ProjectView } from "@/components/projects-view";

export const metadata: Metadata = { title: "Project" };

export default function Page() {
  return (
    <Suspense>
      <ProjectView />
    </Suspense>
  );
}
