import Link from "next/link";

import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="grid min-h-[60dvh] place-items-center px-6 text-center">
      <div>
        <p className="text-muted-foreground font-mono text-sm">404</p>
        <h1 className="mt-2 text-xl font-semibold">Nothing here</h1>
        <Button asChild variant="outline" size="sm" className="mt-6">
          <Link href="/">Back home</Link>
        </Button>
      </div>
    </div>
  );
}
