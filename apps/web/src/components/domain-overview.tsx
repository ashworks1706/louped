import Link from "next/link";

import { AxisExperiments } from "@/components/experiments-list";
import { RunsList } from "@/components/runs-list";
import { NAV, type Section } from "@/lib/nav";

const MORE =
  "text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline";

/** A research domain's front page: its tools, its questions, and their latest runs. */
export function DomainOverview({ section }: { section: Exclude<Section, "workspace"> }) {
  const tools = NAV.filter((n) => n.section === section).slice(2);
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-8">
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold tracking-tight">Tools</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {tools.map((t) => (
            <Link
              key={t.href}
              href={t.href}
              className="hover:bg-accent/40 focus-visible:ring-ring/50 flex flex-col gap-2 rounded-xl border p-4 transition-colors outline-none focus-visible:ring-[3px]"
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                <t.icon className="text-muted-foreground size-4" />
                {t.title}
              </span>
              <span className="text-muted-foreground text-sm">{t.description}</span>
            </Link>
          ))}
        </div>
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold tracking-tight">Questions</h2>
        <AxisExperiments axis={section} />
      </section>
      <section className="flex flex-col items-start gap-3">
        <h2 className="text-lg font-semibold tracking-tight">Latest runs</h2>
        <div className="w-full">
          <RunsList axis={section} limit={8} compact />
        </div>
        <Link href="/runs/" className={MORE}>
          All runs
        </Link>
      </section>
    </div>
  );
}
