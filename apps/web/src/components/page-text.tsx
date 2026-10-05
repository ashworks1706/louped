"use client";

import { part, useRules } from "@/components/parts";
import { partId } from "@/lib/parts";

/** A page's name in addresses: its path as words, page/runs, page/behavior-vectors. */
const pageName = (href: string) => href.split("/").filter(Boolean).join("-") || "home";

/** A page's title and purpose, as parts the layout can rename or (the purpose) hide. */
export function PageText({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  const rule = useRules();
  const at = (what: string) => `${partId("page", pageName(href))}/${what}`;
  const purpose = rule(at("description"));
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight" {...part(at("title"))}>
        {rule(at("title")).label ?? title}
      </h1>
      {!purpose.hidden && (
        <p className="text-muted-foreground text-sm" {...part(at("description"))}>
          {purpose.label ?? description}
        </p>
      )}
    </>
  );
}
