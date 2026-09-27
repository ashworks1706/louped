import type { NavItem } from "@/lib/nav";

/** Title and one-line purpose. `phase` marks a page whose data arrives in a later roadmap phase. */
export function PageHeader({ item, phase }: { item: NavItem; phase?: number }) {
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-5xl flex-col gap-1 px-6 py-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{item.title}</h1>
          {phase !== undefined && (
            <span className="text-muted-foreground rounded-full border px-2 py-0.5 font-mono text-[11px]">
              phase {phase}
            </span>
          )}
        </div>
        <p className="text-muted-foreground text-sm">{item.description}</p>
      </div>
    </header>
  );
}
