"use client";

import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard } from "lucide-react";
import { useQueryState } from "nuqs";

import { BoardFigure } from "@/components/board";
import { EmptyState } from "@/components/empty-state";
import { Help } from "@/components/help";
import { PageHeader } from "@/components/page-header";
import { part, partId } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { q } from "@/lib/api";
import { boardItem } from "@/lib/nav";

/** A board shown as a page of its own: boards/<name>.json at the project's root. */
export function BoardPage() {
  const [name] = useQueryState("name");
  const board = useQuery({ ...q.board(name ?? ""), enabled: !!name });
  if (!name)
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={LayoutDashboard}
          title="No board named"
          body="A board is boards/<name>.json in the project. Ask your agent for one."
          action={{ href: "/", label: "Home" }}
        />
      </section>
    );
  return (
    <QueryState query={board}>
      {(view) => (
        <>
          <PageHeader item={boardItem({ name, ...view })} />
          <section
            {...part(partId("board", name))}
            className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-8"
          >
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
              {view.note}
              <Help label="How to read this board">
                A control, or a click on a mark, row or node, filters the panels that use it. Click
                it again to let it go.
              </Help>
            </p>
            <BoardFigure view={view} name={name} />
          </section>
        </>
      )}
    </QueryState>
  );
}
