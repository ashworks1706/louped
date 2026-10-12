import { PageText } from "@/components/page-text";
import type { NavItem } from "@/lib/nav";

/** Title and one-line purpose. */
export function PageHeader({ item, title }: { item: NavItem; title?: string }) {
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-8">
        <PageText href={item.href} title={title ?? item.title} description={item.description} />
      </div>
    </header>
  );
}
