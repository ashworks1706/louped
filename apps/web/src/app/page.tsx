import { ArrowUpRight, BookOpen } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { RunsList } from "@/components/runs-list";
import { NAV, navItem } from "@/lib/nav";

export default function Home() {
  return (
    <>
      <PageHeader item={navItem("/")} />
      <section className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-8">
        <div>
          <h2 className="text-muted-foreground mb-3 text-sm font-medium">Recent runs</h2>
          <RunsList limit={5} compact />
        </div>
        <div>
          <h2 className="text-muted-foreground mb-3 text-sm font-medium">Everything in loupe</h2>
          <div className="bg-border grid gap-px overflow-hidden rounded-xl border sm:grid-cols-2 lg:grid-cols-3">
            {NAV.filter((n) => n.href !== "/").map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="group bg-background hover:bg-accent/50 flex flex-col gap-2 p-5 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <item.icon className="text-muted-foreground size-4" />
                  <ArrowUpRight className="text-muted-foreground size-4 opacity-0 transition-opacity group-hover:opacity-100" />
                </div>
                <div className="font-medium">{item.title}</div>
                <p className="text-muted-foreground text-sm">{item.description}</p>
              </Link>
            ))}
            <a
              href="https://github.com/ashworks1706/loupe/tree/main/docs"
              target="_blank"
              rel="noreferrer"
              className="group bg-background hover:bg-accent/50 flex flex-col gap-2 p-5 transition-colors"
            >
              <div className="flex items-center justify-between">
                <BookOpen className="text-muted-foreground size-4" />
                <ArrowUpRight className="text-muted-foreground size-4 opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
              <div className="font-medium">Docs</div>
              <p className="text-muted-foreground text-sm">
                Architecture, roadmap and how to extend loupe.
              </p>
            </a>
          </div>
        </div>
      </section>
    </>
  );
}
