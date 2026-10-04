import Image, { type StaticImageData } from "next/image";
import Link from "next/link";

import { CopyCommand } from "@/components/copy-command";
import { docsRoute, repoUrl, tagline } from "@/lib/shared";

import experimentDark from "../../../public/demo/experiment-dark.png";
import experimentLight from "../../../public/demo/experiment-light.png";
import hardwareDark from "../../../public/demo/hardware-dark.png";
import homeDark from "../../../public/demo/home-dark.png";
import homeLight from "../../../public/demo/home-light.png";
import hardwareLight from "../../../public/demo/hardware-light.png";
import itemDark from "../../../public/demo/item-dark.png";
import itemLight from "../../../public/demo/item-light.png";
import itemsDark from "../../../public/demo/items-dark.png";
import itemsLight from "../../../public/demo/items-light.png";
import launchDark from "../../../public/demo/launch-dark.png";
import launchLight from "../../../public/demo/launch-light.png";
import tracesDark from "../../../public/demo/traces-dark.png";
import tracesLight from "../../../public/demo/traces-light.png";

const INSTALL = "pip install 'loupelab[server,tracking,interp,agent]'";

/** The way a question goes through loupe, each step with the screen it happens on. */
const STEPS: {
  title: string;
  text: string;
  code?: string;
  shot: [StaticImageData, StaticImageData];
  alt: string;
}[] = [
  {
    title: "Make a project",
    text: "loupe init writes the project: experiments/ for your questions, an example that runs on a CPU, and AGENTS.md, an MCP server and skills for the coding agent you already use. What loupe writes goes to .loupe/, out of git.",
    code: `${INSTALL}\nloupe init my-research && cd my-research\nloupe serve`,
    shot: [homeLight, homeDark],
    alt: "A new project opened in the app: its example question and runs",
  },
  {
    title: "Ask, and let your agent write it",
    text: "Tell Claude Code, Codex or Cursor what you want to test. It starts the experiment through loupe's MCP server and writes the README before the code: the question, competing hypotheses, a baseline, the test and when to stop.",
    shot: [experimentLight, experimentDark],
    alt: "The experiment the agent wrote, read in the app",
  },
  {
    title: "Run it here, or on your cluster",
    text: "A small check runs on this machine and shows live. A real run exports to Sol, a Slurm cluster or a VM as one job.sh, and its result imports back as if it ran here. Models loupe does not load, such as GGUF on llama-server or your own engine, are evaluated and timed through their endpoint.",
    shot: [launchLight, launchDark],
    alt: "Launch: the experiment's options as a form, here or on a cluster",
  },
  {
    title: "Read it item by item",
    text: "Every item under every condition, against the baseline's fixed cohort: what flipped, out of how many, with Wilson intervals. Open one to see each condition side by side, with the scores behind the answer.",
    shot: [itemLight, itemDark],
    alt: "One question under baseline, evidence and pushback, side by side",
  },
];

const MORE: {
  title: string;
  text: string;
  shot: [StaticImageData, StaticImageData];
  alt: string;
}[] = [
  {
    title: "What it cost",
    text: "Every run records the machine while it ran: GPU energy, power, memory and utilisation, CPU and RAM, next to its provenance (code, packages, seed, command).",
    shot: [hardwareLight, hardwareDark],
    alt: "A run's results with the GPU energy and hardware it used",
  },
  {
    title: "Agent traces as timelines",
    text: "An agent's trace files read per request: each event's offset and duration, what it carried, every field on a click. loupe view opens a folder of them, or any results you already have, read-only.",
    shot: [tracesLight, tracesDark],
    alt: "Agent requests as timelines of retrieval, model calls and tools",
  },
];

function Shot({
  shot: [light, dark],
  alt,
  priority = false,
}: {
  shot: [StaticImageData, StaticImageData];
  alt: string;
  priority?: boolean;
}) {
  return (
    <div className="w-full overflow-hidden rounded-xl border shadow-2xl shadow-black/5">
      <Image src={light} alt={alt} priority={priority} className="dark:hidden" />
      <Image src={dark} alt={alt} priority={priority} className="hidden dark:block" />
    </div>
  );
}

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center px-6 pt-24 pb-16 md:pt-32">
      <h1 className="max-w-2xl text-center text-4xl font-semibold tracking-tight text-balance md:text-6xl">
        {tagline}
      </h1>
      <p className="text-fd-muted-foreground mt-5 max-w-lg text-center text-balance">
        Each research question an experiment, written and run by your coding agent, read item by
        item by you. Local, on open models, and free.
      </p>
      <div className="mt-10 flex max-w-full flex-wrap items-center justify-center gap-3">
        <CopyCommand command={INSTALL} />
        <Link
          href={`${docsRoute}/quickstart`}
          className="bg-fd-primary text-fd-primary-foreground inline-flex h-10.5 items-center rounded-lg px-5 text-sm font-medium hover:opacity-90"
        >
          Get started
        </Link>
      </div>

      <div className="mt-20 w-full">
        <Shot
          shot={[itemsLight, itemsDark]}
          alt="Sixteen questions under three conditions: what pushback and evidence did to each answer"
          priority
        />
      </div>

      <section className="mt-28 flex w-full flex-col gap-20" aria-labelledby="how">
        <h2 id="how" className="text-center text-2xl font-semibold tracking-tight md:text-3xl">
          How it works
        </h2>
        {STEPS.map((step, i) => (
          <div
            key={step.title}
            className="grid items-start gap-8 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
          >
            <div className="flex flex-col gap-3 md:sticky md:top-24">
              <span className="text-fd-muted-foreground font-mono text-xs">0{i + 1}</span>
              <h3 className="text-lg font-semibold tracking-tight">{step.title}</h3>
              <p className="text-fd-muted-foreground text-sm leading-relaxed">{step.text}</p>
              {step.code && (
                <pre className="bg-fd-card overflow-x-auto rounded-lg border p-3 font-mono text-xs leading-relaxed">
                  {step.code}
                </pre>
              )}
            </div>
            <Shot shot={step.shot} alt={step.alt} />
          </div>
        ))}
      </section>

      <section className="mt-28 grid w-full gap-12 md:grid-cols-2" aria-label="More">
        {MORE.map((m) => (
          <div key={m.title} className="flex flex-col gap-4">
            <div>
              <h3 className="text-lg font-semibold tracking-tight">{m.title}</h3>
              <p className="text-fd-muted-foreground mt-1 text-sm leading-relaxed">{m.text}</p>
            </div>
            <Shot shot={m.shot} alt={m.alt} />
          </div>
        ))}
      </section>

      <section className="mt-28 w-full rounded-xl border p-8 text-center">
        <h2 className="text-xl font-semibold tracking-tight">Bring your own agent</h2>
        <p className="text-fd-muted-foreground mx-auto mt-2 max-w-xl text-sm text-balance">
          loupe has no agent of its own. It is the harness for the one you use: an MCP server,
          skills and an AGENTS.md that hold the method (fixed cohorts, counts with denominators,
          paired intervals, provenance on every result). In Claude Code it is also a plugin.
        </p>
        <div className="mt-5 flex justify-center">
          <CopyCommand command="/plugin marketplace add ashworks1706/loupe" />
        </div>
      </section>

      <footer className="text-fd-muted-foreground mt-32 flex w-full justify-between border-t pt-6 text-sm">
        <span>Apache 2.0</span>
        <a href={repoUrl} className="hover:text-fd-foreground">
          GitHub
        </a>
      </footer>
    </main>
  );
}
