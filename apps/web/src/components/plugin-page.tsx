"use client";

import { useQuery } from "@tanstack/react-query";
import { Puzzle } from "lucide-react";
import { useTheme } from "next-themes";
import { useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { QueryState } from "@/components/query-state";
import { API, q, type PluginInfo } from "@/lib/api";
import { pluginItem } from "@/lib/nav";

/** The tokens a panel is handed, so it reads as part of the app: var(--foreground) and the rest. */
const TOKENS = [
  "radius",
  "background",
  "foreground",
  "card",
  "card-foreground",
  "popover",
  "popover-foreground",
  "primary",
  "primary-foreground",
  "secondary",
  "secondary-foreground",
  "muted",
  "muted-foreground",
  "accent",
  "accent-foreground",
  "border",
  "input",
  "ring",
  "intervention",
  "positive",
  "negative",
  "font-geist-sans",
  "font-geist-mono",
];

/** A project plugin's page: its panel, its load error, or what it adds without one. */
export function PluginPage() {
  const [name] = useQueryState("name");
  const plugins = useQuery(q.plugins());
  return (
    <QueryState query={plugins}>
      {(all) => {
        const plugin = all.find((p) => p.name === name);
        if (!plugin)
          return (
            <section className="mx-auto max-w-6xl px-6 py-8">
              <EmptyState
                icon={Puzzle}
                title="No such plugin"
                body="A plugin is a folder under the project's plugins/ with a plugin.toml."
                action={{ href: "/", label: "Home" }}
              />
            </section>
          );
        return (
          <>
            <PageHeader item={pluginItem(plugin)} />
            <section className="mx-auto max-w-6xl px-6 py-8">
              <Body plugin={plugin} />
            </section>
          </>
        );
      }}
    </QueryState>
  );
}

function Body({ plugin }: { plugin: PluginInfo }) {
  if (plugin.error)
    return (
      <div className="flex flex-col gap-2">
        <p className="text-negative text-sm">plugins/{plugin.name}/plugin.py did not load:</p>
        <pre className="bg-muted overflow-x-auto rounded-md p-3 font-mono text-xs">
          {plugin.error}
        </pre>
      </div>
    );
  if (!plugin.panel)
    return (
      <p className="text-muted-foreground text-sm">
        {plugin.run || plugin.experiment
          ? `It adds a tab to each ${[plugin.run && "run", plugin.experiment && "experiment"].filter(Boolean).join(" and ")}, and no page of its own`
          : "It adds routes, commands or agent tools, and no page"}
        : a page is <span className="font-mono">plugins/{plugin.name}/panel/index.html</span>.
      </p>
    );
  return <PluginFrame name={plugin.name} />;
}

/** A plugin's page in a frame (its own page, or its run or experiment tab with that one's id),
 * handed the app's theme each time it loads or the theme changes. */
export function PluginFrame({
  name,
  page = "",
  query,
  fit = false,
}: {
  name: string;
  /** A page of its panel/, such as run.html; the panel's index when empty. */
  page?: string;
  query?: Record<string, string>;
  /** A block in a layout: as tall as the page says it is (the kit's louped.js says so). */
  fit?: boolean;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState<number | null>(null);
  useEffect(() => {
    if (!fit) return;
    const onMessage = (e: MessageEvent<{ type?: string; height?: number }>) => {
      if (e.source !== frame.current?.contentWindow || e.data?.type !== "louped:height") return;
      if (typeof e.data.height === "number") setHeight(Math.ceil(e.data.height));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [fit]);
  const { resolvedTheme } = useTheme();
  const theme = () => {
    const doc = frame.current?.contentDocument;
    // between loads a frame's document can be empty; onLoad themes it once it is there
    if (!doc?.documentElement || !doc.head) return;
    const style = getComputedStyle(document.body);
    for (const t of TOKENS)
      doc.documentElement.style.setProperty(`--${t}`, style.getPropertyValue(`--${t}`));
    doc.documentElement.classList.toggle("dark", resolvedTheme === "dark");
    doc.documentElement.style.setProperty(
      "color-scheme",
      resolvedTheme === "dark" ? "dark" : "light",
    );
    // the app's fonts are declared in its own sheets, which a frame does not see
    if (!doc.getElementById("louped-fonts")) {
      const fonts = Object.assign(doc.createElement("style"), { id: "louped-fonts" });
      fonts.textContent = [...document.styleSheets]
        .flatMap((sheet) => {
          try {
            return [...sheet.cssRules];
          } catch {
            return []; // another origin's sheet cannot be read, and holds none of the app's fonts
          }
        })
        .filter((rule) => rule instanceof CSSFontFaceRule)
        // its urls are relative to the sheet, not the frame
        .map((rule) =>
          rule.cssText.replace(
            /url\("([^"]+)"\)/g,
            (_, u: string) =>
              `url("${new URL(u, rule.parentStyleSheet?.href ?? location.href).href}")`,
          ),
        )
        .join("\n");
      doc.head.append(fonts);
    }
  };
  useEffect(theme); // after every render: the theme may have changed
  return (
    <iframe
      ref={frame}
      title={name}
      src={`${API}/x/${encodeURIComponent(name)}/${page}${query ? `?${new URLSearchParams(query)}` : ""}`}
      onLoad={theme}
      style={fit && height !== null ? { height } : undefined}
      className={
        fit ? "min-h-16 w-full" : "h-[calc(100dvh-14rem)] min-h-96 w-full rounded-xl border"
      }
    />
  );
}
