"use client";

import { useQuery } from "@tanstack/react-query";

import { Help } from "@/components/help";
import { Markdown } from "@/components/markdown";
import { PluginFrame } from "@/components/plugin-page";
import { isSnapshot, q, type Block, type UiPage } from "@/lib/api";
import { partId } from "@/lib/parts";
import { cn } from "@/lib/utils";

/** A page's regions, as louped.server.ui names them. */
export type Region = "home" | "run.tabs" | "run.overview" | "experiment.tabs" | "experiment.design";

/** What a page's regions show: an experiment's layout.json over the project's over a preset over
 * the default. It follows the files while an agent edits them, where launching is on. */
export function useLayout(experiment?: string | null) {
  const health = useQuery(q.health());
  const poll = health.data?.launching === true && !isSnapshot();
  return useQuery(q.layout(experiment, poll));
}

/** louped.toml's [theme] over the app's tokens, followed while launching. */
export function ThemeTokens() {
  const health = useQuery(q.health());
  const theme = useQuery(q.theme(health.data?.launching === true && !isSnapshot()));
  if (!theme.data) return null;
  const css = (tokens: Record<string, string>) =>
    Object.entries(tokens)
      .map(([k, v]) => `--${k}: ${v};`)
      .join(" ");
  // more specific than globals.css's :root and .dark, so these win in their mode
  return (
    <style id="louped-theme">{`:root:not(.dark) { ${css(theme.data.light)} } :root.dark { ${css(theme.data.dark)} }`}</style>
  );
}

/** A block's address on the page, which Shift+click hands the person's agent:
 * "<region>/<block>", then what picks it out (a metric's key, a file, a figure, a plugin, or a
 * text block's place in its region). */
export function blockId(region: Region, b: Block, at?: number): string {
  const which =
    b.key ??
    b.path ??
    (b.index != null ? String(b.index) : null) ??
    b.plugin ??
    (b.block === "text" && at !== undefined ? String(at) : null);
  return which != null ? partId(`${region}/${b.block}`, which) : `${region}/${b.block}`;
}

/** A text block: the layout's own Markdown. */
export const textBlock = (b: Block): { title?: string; about?: string; body: React.ReactNode } => ({
  body: (
    <div className="max-w-3xl text-sm">
      <Markdown>{b.text ?? ""}</Markdown>
    </div>
  ),
});

/** What is wrong with the layout files or the theme; the page meanwhile shows what is below them. */
export function LayoutErrors({ page }: { page: UiPage | undefined }) {
  const health = useQuery(q.health());
  const theme = useQuery(q.theme(false));
  const layout = page?.errors ?? [];
  const tokens = theme.data?.errors ?? [];
  if ((layout.length === 0 && tokens.length === 0) || !health.data?.launching) return null;
  return (
    <div
      role="alert"
      className="border-negative/30 bg-negative/5 mb-6 flex flex-col gap-1 rounded-xl border px-4 py-3 text-xs"
    >
      {layout.length > 0 && (
        <>
          <p className="text-negative font-medium">
            Not used, so the page shows the layout below them:
          </p>
          <ul className="text-muted-foreground font-mono">
            {layout.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </>
      )}
      {tokens.length > 0 && (
        <>
          <p className="text-negative font-medium">
            Theme values dropped, so the app keeps its own:
          </p>
          <ul className="text-muted-foreground font-mono">
            {tokens.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** A region's blocks in order: full or half width, and side blocks in a narrow column beside the
 * rest. render returns null for a block with nothing to show on this page (no error, no
 * report), which then takes no space. */
export function RegionGrid({
  region,
  blocks,
  render,
  roomy = false,
}: {
  region: Region;
  blocks: Block[];
  /** A page's sections (Home), spaced and titled as such, not a tab's blocks. */
  roomy?: boolean;
  render: (b: Block) => { title?: string; about?: string; body: React.ReactNode } | null;
}) {
  const drawn = blocks.flatMap((b, at) => {
    const got = b.block === "text" ? textBlock(b) : render(b);
    return got ? [{ b, at, ...got }] : [];
  });
  const cell = ({ b, at, title, about, body }: (typeof drawn)[number]) => (
    <section
      key={`${blockId(region, b, at)}@${at}`}
      data-part={blockId(region, b, at)}
      className={cn(
        "flex min-w-0 flex-col",
        roomy ? "items-start gap-3 [&>*]:w-full [&>a]:w-auto" : "gap-2",
        b.width !== "half" && "lg:col-span-2",
      )}
    >
      {(b.title ?? title) && (
        <h2
          className={cn(
            "flex items-center gap-1.5",
            roomy ? "text-lg font-semibold tracking-tight" : "text-sm font-medium",
          )}
        >
          {b.title ?? title}
          {(b.about ?? about) && <Help>{(b.about ?? about)!}</Help>}
        </h2>
      )}
      {body}
    </section>
  );
  const main = drawn.filter((d) => d.b.width !== "side");
  const side = drawn.filter((d) => d.b.width === "side");
  const grid = (
    <div className={cn("grid grid-cols-1 lg:grid-cols-2", roomy ? "gap-10" : "gap-6")}>
      {main.map(cell)}
    </div>
  );
  if (side.length === 0) return grid;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="min-w-0">{grid}</div>
      <aside className="order-first flex flex-col gap-6 lg:sticky lg:top-6 lg:order-none lg:self-start">
        {side.map(cell)}
      </aside>
    </div>
  );
}

/** A plugin block: its page from panel/, sized to what it draws when it uses the kit. */
export function PluginBlock({
  b,
  page,
  query,
}: {
  b: Block;
  page: string;
  query?: Record<string, string>;
}) {
  return (
    <PluginFrame name={b.plugin!} page={b.page ?? page} query={{ ...query, block: "1" }} fit />
  );
}
