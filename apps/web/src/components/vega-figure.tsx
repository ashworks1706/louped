"use client";

import { useTheme } from "next-themes";
import type { VisualizationSpec } from "vega-embed";
import { useEffect, useRef, useState } from "react";

import type { VegaView } from "@/lib/api";

/** Whether a spec names a url anywhere Vega reads one: not inside its rows (`values`). */
const loads = (spec: unknown): boolean =>
  Array.isArray(spec)
    ? spec.some(loads)
    : typeof spec === "object" &&
      spec !== null &&
      Object.entries(spec).some(([k, v]) => k === "url" || (k !== "values" && loads(v)));

/** Reads a token's current value, so the chart follows the theme. */
const token = (el: Element, name: string) => getComputedStyle(el).getPropertyValue(name).trim();

/** A Vega-Lite spec drawn in the app's theme. Data is inline only: a spec naming a url is not
 * drawn, and the loader refuses every load besides, so a shared run's chart fetches nothing. */
export function VegaFigure({
  view,
  onMark,
}: {
  view: VegaView;
  onMark?: (key: string | null, picked: boolean) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();
  const mark = useRef(onMark);
  useEffect(() => {
    mark.current = onMark;
  }, [onMark]);
  const field = view.items?.field;
  const remote = loads(view.spec);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let done = false;
    let finalize = () => {};
    if (remote) return;
    void (async () => {
      const [{ default: embed }, { loader }] = await Promise.all([
        import("vega-embed"),
        import("vega"),
      ]);
      const ink = token(el, "--foreground");
      const muted = token(el, "--muted-foreground");
      const line = token(el, "--border");
      // SVG attributes do not resolve var(): the fonts' own family names
      const sans = token(el, "--font-geist-sans") || "sans-serif";
      const mono = token(el, "--font-geist-mono") || "monospace";
      const axis = {
        domainColor: line,
        gridColor: line,
        tickColor: line,
        labelColor: muted,
        titleColor: muted,
        labelFont: mono,
        titleFont: sans,
        titleFontWeight: 400 as const,
      };
      const refuse = loader();
      refuse.load = () => Promise.reject(new Error("data must be inline"));
      try {
        // as wide as the figure unless the spec says otherwise
        const spec = { width: "container", ...view.spec } as VisualizationSpec;
        const result = await embed(el, spec, {
          actions: false,
          renderer: "svg",
          loader: refuse,
          tooltip: { theme: "custom" },
          config: {
            background: "transparent",
            font: sans,
            view: { stroke: "transparent" },
            axis,
            legend: { labelColor: muted, titleColor: muted, labelFont: mono },
            title: { color: ink },
            range: { category: [ink, token(el, "--intervention"), muted] },
            mark: { color: ink, tooltip: true },
          },
        });
        if (field) {
          // the item a mark stands for: the datum's key field, when the figure names one
          const keyOf = (item: unknown) => {
            const datum = (item as { datum?: Record<string, unknown> } | null)?.datum;
            const v = datum?.[field];
            return v == null ? null : String(v);
          };
          result.view.addEventListener("mouseover", (_, item) =>
            mark.current?.(keyOf(item), false),
          );
          result.view.addEventListener("mouseout", () => mark.current?.(null, false));
          result.view.addEventListener("click", (_, item) => {
            const key = keyOf(item);
            if (key !== null) mark.current?.(key, true);
          });
        }
        if (done) result.finalize();
        else finalize = () => result.finalize();
        setError(null);
      } catch (e) {
        if (!done) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      done = true;
      finalize();
    };
  }, [view.spec, resolvedTheme, remote, field]);
  const said = remote ? "data must be inline (data.values), not loaded from a url" : error;
  return (
    <>
      <div ref={ref} className="w-full overflow-x-auto" />
      {said && <p className="text-negative text-sm">This chart could not be drawn: {said}</p>}
    </>
  );
}
