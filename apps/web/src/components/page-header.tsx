import type { NavItem } from "@/lib/nav";

/** Title and one-line purpose. */
export function PageHeader({ item }: { item: NavItem }) {
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">{item.title}</h1>
        <p className="text-muted-foreground text-sm">{item.description}</p>
      </div>
    </header>
  );
}
