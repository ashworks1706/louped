import Link from "next/link";

import { ActiveExperiments } from "@/components/experiments-list";
import { HomeStats, LiveNow } from "@/components/home-overview";
import { PageHeader } from "@/components/page-header";
import { RunsList } from "@/components/runs-list";
import { navItem } from "@/lib/nav";

const MORE =
  "text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline";

export default function Home() {
  return (
    <>
      <PageHeader item={navItem("/")} />
      <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-8">
        <HomeStats />
        <LiveNow />
        <section className="flex flex-col items-start gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Active questions</h2>
          <div className="w-full">
            <ActiveExperiments />
          </div>
          <Link href="/experiments/" className={MORE}>
            All experiments
          </Link>
        </section>
        <section className="flex flex-col items-start gap-3">
          <h2 className="text-lg font-semibold tracking-tight">Latest runs</h2>
          <div className="w-full">
            <RunsList limit={8} compact />
          </div>
          <Link href="/runs/" className={MORE}>
            All runs
          </Link>
        </section>
      </div>
    </>
  );
}
