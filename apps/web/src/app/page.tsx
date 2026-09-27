import { ArrowUpRight, BookOpen, ListTree } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { NAV, navItem } from "@/lib/nav";

export default function Home() {
  return (
    <>
      <PageHeader item={navItem("/")} />
      <section className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-8">
        <div>
          <h2 className="text-muted-foreground mb-3 text-sm font-medium">Recent runs</h2>
          <EmptyState
            icon={ListTree}
            title="Nothing has run yet"
            body="Start the API next to this page, then run an eval. Its results land here."
            command="just serve"
          />
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
