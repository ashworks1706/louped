"use client";

import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";

import type { PlotlyView } from "@/lib/api";

/** Reads a token's current value, so the figure follows the theme. */
const token = (el: Element, name: string) => getComputedStyle(el).getPropertyValue(name).trim();

/** A Plotly figure in the app's theme: points in 3D, surfaces, figures that play through frames.
 * Plotly loads only when one is shown; the server refuses a figure that names a url. */
export function PlotlyFigure({ view }: { view: PlotlyView }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let done = false;
    let purge = () => {};
    void (async () => {
      const Plotly = (await import("plotly.js-dist-min")).default;
      if (done) return;
      const ink = token(el, "--foreground");
      const muted = token(el, "--muted-foreground");
      const line = token(el, "--border");
      const sans = token(el, "--font-geist-sans") || "sans-serif";
      const axis = { gridcolor: line, zerolinecolor: line, linecolor: line, color: muted };
      // the server requires a name on every frame; the slider steps by it
      const frames = view.frames ?? [];
      const layout = {
        autosize: true,
        height: 420,
        margin: { l: 40, r: 16, t: 16, b: 40 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { family: sans, color: ink, size: 12 },
        colorway: [ink, token(el, "--intervention"), muted],
        xaxis: axis,
        yaxis: axis,
        scene: { xaxis: axis, yaxis: axis, zaxis: axis },
        // frames play from a button and a slider, as Plotly's own animations do
        ...(frames.length > 0 && {
          updatemenus: [
            {
              type: "buttons",
              showactive: false,
              x: 0,
              y: -0.12,
              xanchor: "left",
              buttons: [
                {
                  label: "Play",
                  method: "animate",
                  args: [null, { fromcurrent: true, frame: { duration: 400 } }],
                },
              ],
            },
          ],
          sliders: [
            {
              x: 0.1,
              len: 0.9,
              y: -0.06,
              currentvalue: { prefix: "", font: { color: muted } },
              steps: frames.map((f) => ({
                label: String(f.name),
                method: "animate",
                args: [[f.name], { mode: "immediate", frame: { duration: 0 } }],
              })),
            },
          ],
        }),
        ...view.layout,
      };
      try {
        await Plotly.newPlot(el, view.data as Plotly.Data[], layout as Partial<Plotly.Layout>, {
          displaylogo: false,
          responsive: true,
          modeBarButtonsToRemove: ["toImage"],
          // nothing from the web: no map shapes (the server refuses map traces too)
          topojsonURL: "",
        });
        if (frames.length) await Plotly.addFrames(el, frames as Plotly.Frame[]);
        if (done) Plotly.purge(el);
        else purge = () => Plotly.purge(el);
        setError(null);
      } catch (e) {
        if (!done) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      done = true;
      purge();
    };
  }, [view, resolvedTheme]);
  return (
    <>
      <div ref={ref} data-testid="plotly" className="w-full" />
      {error && <p className="text-negative text-sm">This figure could not be drawn: {error}</p>}
    </>
  );
}
