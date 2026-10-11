"use client";

import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";

import type { PlotlyView } from "@/lib/api";

/** Reads a token's current value, so the figure follows the theme. */
const token = (el: Element, name: string) => getComputedStyle(el).getPropertyValue(name).trim();

/** The item a point stands for: its trace's id for it, when the trace names its items. */
const keyOf = (p: Plotly.PlotDatum | undefined) => {
  const ids = (p?.data as { ids?: unknown[] } | undefined)?.ids;
  const id = p && ids?.[p.pointNumber];
  return id == null ? null : String(id);
};

/** How long the camera takes to go once around the scene when the figure orbits. */
const ORBIT_TURN_MS = 24_000;

type PlotlyLib = (typeof import("plotly.js-dist-min"))["default"];
/** plotly_buttonclicked, which Plotly's types leave out. */
type Clicks = {
  on(event: "plotly_buttonclicked", callback: (e: { button: { label: string } }) => void): void;
};

/** Starts the view's motion the first time the figure is in view: plays its frames (autoplay)
 * and turns its 3D scene around the z axis (orbit) while it stays in view. The orbit stops when
 * the person drags, touches or zooms the figure. Returns what stops it all. */
function moveWhenSeen(
  Plotly: PlotlyLib,
  plot: Plotly.PlotlyHTMLElement,
  animation: NonNullable<PlotlyView["animation"]>,
  play: () => void,
): () => void {
  const eye = plot.layout.scene?.camera?.eye ?? {};
  const z = eye.z ?? 1.25;
  const radius = Math.hypot(eye.x ?? 1.25, eye.y ?? 1.25);
  let angle = Math.atan2(eye.y ?? 1.25, eye.x ?? 1.25);
  let seen = false;
  let inView = false;
  let turning = animation.orbit;
  let busy = false;
  let raf = 0;
  let last = performance.now();
  const turn = (now: number) => {
    if (!turning) return;
    raf = requestAnimationFrame(turn);
    const elapsed = now - last;
    last = now;
    if (!inView) return;
    angle += (elapsed / ORBIT_TURN_MS) * 2 * Math.PI;
    if (busy) return; // the last move is still drawing: skip to where the camera is by now
    busy = true;
    const at = { x: radius * Math.cos(angle), y: radius * Math.sin(angle), z };
    // a move fails only when the figure went away while it drew; the next frame does not come
    void Plotly.relayout(plot, { "scene.camera.eye": at } as Partial<Plotly.Layout>).then(
      () => (busy = false),
      () => (turning = false),
    );
  };
  const halt = () => {
    turning = false;
    cancelAnimationFrame(raf);
  };
  const observer = new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    if (inView && !seen) {
      seen = true;
      if (animation.autoplay) play();
    }
  });
  observer.observe(plot);
  plot.addEventListener("pointerdown", halt, { capture: true });
  plot.addEventListener("wheel", halt, { capture: true, passive: true });
  if (turning) raf = requestAnimationFrame(turn);
  return () => {
    halt();
    observer.disconnect();
    plot.removeEventListener("pointerdown", halt, { capture: true });
    plot.removeEventListener("wheel", halt, { capture: true });
  };
}

/** A Plotly figure in the app's theme: points in 3D, surfaces, figures that play through frames.
 * Plotly loads only when one is shown; the server refuses a figure that names a url. With
 * onMark, hovering a point says which item it stands for and clicking one picks it. The view's
 * animation plays the frames when the figure comes into view (again from the first with loop) and
 * turns a 3D scene (orbit) until the person drags or zooms it; with reduced motion asked for,
 * nothing moves by itself and Play stays. */
export function PlotlyFigure({
  view,
  onMark,
}: {
  view: PlotlyView;
  onMark?: (key: string | null, picked: boolean) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();
  const mark = useRef(onMark);
  useEffect(() => {
    mark.current = onMark;
  }, [onMark]);
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
      const names = frames.map((f) => String(f.name));
      const animation = view.animation;
      const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const step = {
        frame: { duration: animation?.duration_ms ?? 400 },
        transition: { duration: animation?.transition_ms ?? 0 },
      };
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
        // frames play from buttons and a slider, as Plotly's own animations do; Play is handled
        // below (plotly_buttonclicked), so that it loops when the view asks; the buttons have a
        // row of their own under the slider, so a narrow figure does not put them over it
        ...(frames.length > 0 && {
          updatemenus: [
            {
              type: "buttons",
              direction: "left",
              showactive: false,
              x: 0,
              y: 0,
              xanchor: "left",
              yanchor: "top",
              pad: { t: 116 },
              buttons: [
                { label: "Play", method: "skip", args: [] },
                {
                  label: "Pause",
                  method: "animate",
                  args: [[null], { mode: "immediate", frame: { duration: 0 } }],
                },
              ],
            },
          ],
          sliders: [
            {
              x: 0,
              len: 1,
              y: 0,
              yanchor: "top",
              pad: { t: 24 },
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
        const plot = el as unknown as Plotly.PlotlyHTMLElement;
        plot.on("plotly_hover", (e) => mark.current?.(keyOf(e.points[0]), false));
        plot.on("plotly_unhover", () => mark.current?.(null, false));
        plot.on("plotly_click", (e) => {
          const key = keyOf(e.points[0]);
          if (key !== null) mark.current?.(key, true);
        });
        // Plotly.animate settles when the frames end, and fails when Pause or the slider stops it
        const play = (fromcurrent: boolean) => {
          Plotly.animate(el, names, { ...step, mode: "immediate", fromcurrent }).then(
            () => {
              if (animation?.loop && !done) play(false);
            },
            () => {},
          );
        };
        (plot as unknown as Clicks).on("plotly_buttonclicked", (e) => {
          if (e.button.label === "Play") play(true);
        });
        const stop =
          !still && (animation?.autoplay || animation?.orbit)
            ? moveWhenSeen(Plotly, plot, animation, () => play(false))
            : () => {};
        purge = () => {
          stop();
          Plotly.purge(el);
        };
        if (done) purge();
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
