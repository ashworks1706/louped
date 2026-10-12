import { Suspense } from "react";

import { Moved } from "@/components/moved";

/** An old address: sends the visitor to where the page is now. */
export default function Page() {
  return (
    <Suspense>
      <Moved />
    </Suspense>
  );
}
