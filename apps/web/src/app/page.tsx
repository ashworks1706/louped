import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { RunsList } from "@/components/runs-list";
import { navItem } from "@/lib/nav";

export default function Home() {
  return (
    <>
      <PageHeader item={navItem("/")} />
      <section className="mx-auto flex max-w-6xl flex-col items-start gap-2 px-6 py-8">
        <div className="w-full">
          <RunsList limit={10} compact />
        </div>
        <Link
          href="/runs/"
          className="text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline"
        >
          All runs
        </Link>
      </section>
    </>
  );
}
