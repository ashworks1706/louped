import Image, { type StaticImageData } from "next/image";
import Link from "next/link";

import { CopyCommand } from "@/components/copy-command";
import { docsRoute, repoUrl, tagline } from "@/lib/shared";

import experimentDark from "../../../public/demo/experiment-dark.png";
import experimentLight from "../../../public/demo/experiment-light.png";
import figureDark from "../../../public/demo/figure-dark.png";
import figureLight from "../../../public/demo/figure-light.png";
import homeDark from "../../../public/demo/home-dark.png";
import homeLight from "../../../public/demo/home-light.png";
import itemDark from "../../../public/demo/item-dark.png";
import itemLight from "../../../public/demo/item-light.png";
import itemsDark from "../../../public/demo/items-dark.png";
import itemsLight from "../../../public/demo/items-light.png";
import launchDark from "../../../public/demo/launch-dark.png";
import launchLight from "../../../public/demo/launch-light.png";
import picksDark from "../../../public/demo/picks-dark.png";
import picksLight from "../../../public/demo/picks-light.png";

const INSTALL = "pip install 'louped[server,tracking,interp,agent]'";

type Shot = [StaticImageData, StaticImageData];

const STEPS: { title: string; text: string; code?: string; shot: Shot; alt: string }[] = [
  {
    title: "Make a project",
    text: "One command sets up a folder for your questions, an example to try, and the files your coding agent needs.",
    code: `${INSTALL}\nlouped init my-research && cd my-research\nlouped serve`,
    shot: [homeLight, homeDark],
    alt: "A project's home: its domains and active questions",
  },
  {
    title: "Ask your agent",
    text: "Tell Claude Code, Codex or Cursor what to test. It writes the experiment: the question, the plan and the script.",
    shot: [experimentLight, experimentDark],
    alt: "An experiment's page: its question, hypotheses, test and result",
  },
  {
    title: "Run it",
    text: "The script's options become a form. Small runs go on your machine. Large ones go to a Slurm cluster as one job, and the results come back to your app.",
    shot: [launchLight, launchDark],
    alt: "The launch form for an experiment's script, with its options",
  },
  {
    title: "Read the results",
    text: "See every item under every condition: what changed against the reference, out of how many, with a 95% interval.",
    shot: [itemsLight, itemsDark],
    alt: "Fifty items under three conditions, each against the reference",
  },
  {
    title: "Point your agent at it",
    text: "Shift+click rows, cards or fields. Your agent reads what you picked, with its data, and points back at the evidence on screen. Ask it to change any part of a page, or add a page of its own.",
    shot: [picksLight, picksDark],
    alt: "Three rows picked on the Items tab, with the tray your agent reads",
  },
];

const MORE: { title: string; text: string; shot: Shot; alt: string }[] = [
  {
    title: "Each answer, side by side",
    text: "Open an item to read what the model said under each condition. Fields that differ from the reference are outlined.",
    shot: [itemLight, itemDark],
    alt: "One question with the model's answer with the vector added, left out and subtracted",
  },
  {
    title: "Every point traces back",
    text: "Hover a point in a figure to see its item, the files that hold it and the script that drew it. Click it to open the item.",
    shot: [figureLight, figureDark],
    alt: "A scatter of items, one hovered, with the item and files it traces to",
  },
];

function Screenshot({ shot: [light, dark], alt }: { shot: Shot; alt: string }) {
  return (
    <div className="w-full overflow-hidden rounded-xl border shadow-2xl shadow-black/5">
      <Image src={light} alt={alt} className="dark:hidden" />
      <Image src={dark} alt={alt} className="hidden dark:block" />
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
        Your coding agent writes and runs the experiments, and shapes the app around them. You read
        the results, item by item. Local, open models, free.
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

      <figure className="mt-20 w-full">
        <video
          className="w-full rounded-xl border shadow-2xl shadow-black/5"
          src="/demo/demo.mp4"
          poster="/demo/demo-poster.jpg"
          aria-label="A researcher asks their coding agent a question; the agent writes and runs the experiment, points at the results in louped, and answers about the items the researcher picks"
          autoPlay
          muted
          loop
          playsInline
          controls
        />
        <figcaption className="text-fd-muted-foreground mt-3 text-center text-xs text-balance">
          A researcher and their agent re-read CAA&apos;s released Llama 2 7B Chat results. The app
          and its numbers are real; the agent&apos;s lines are scripted.
        </figcaption>
      </figure>

      <section className="mt-28 flex w-full flex-col gap-20" aria-labelledby="how">
        <h2 id="how" className="text-center text-2xl font-semibold tracking-tight md:text-3xl">
          How it works
        </h2>
        {STEPS.map((step, i) => (
          <div
            key={step.title}
            className="grid grid-cols-1 items-start gap-8 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
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
            <Screenshot shot={step.shot} alt={step.alt} />
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
            <Screenshot shot={m.shot} alt={m.alt} />
          </div>
        ))}
      </section>

      <section className="mt-28 w-full rounded-xl border p-8 text-center">
        <h2 className="text-xl font-semibold tracking-tight">Use your own agent</h2>
        <p className="text-fd-muted-foreground mx-auto mt-2 max-w-xl text-sm text-balance">
          louped works with the coding agent you already use. In Claude Code, you can also add it as
          a plugin.
        </p>
        <div className="mt-5 flex justify-center">
          <CopyCommand command="/plugin marketplace add ashworks1706/louped" />
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
