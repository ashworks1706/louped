import { DOMAINS, type NavItem } from "@/lib/nav";

/** Title and one-line purpose. A domain's page names its domain above the title; its overview is
 * titled by the domain itself. */
export function PageHeader({ item, title }: { item: NavItem; title?: string }) {
  const domain = DOMAINS.find((d) => d.section === item.section);
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-1 px-6 py-8">
        {domain && !title && (
          <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
            <domain.icon className="size-3.5" />
            {domain.title}
          </p>
        )}
        <h1 className="text-2xl font-semibold tracking-tight">{title ?? item.title}</h1>
        <p className="text-muted-foreground text-sm">{item.description}</p>
      </div>
    </header>
  );
}
