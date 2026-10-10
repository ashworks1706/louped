import type { Metadata } from "next";
import { Suspense } from "react";

import { BoardPage } from "@/components/board-page";

export const metadata: Metadata = { title: "Board" };

export default function Page() {
  return (
    <Suspense>
      <BoardPage />
    </Suspense>
  );
}
