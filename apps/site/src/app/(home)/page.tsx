import Link from "next/link";

import { CopyCommand } from "@/components/copy-command";
import { Mark } from "@/components/mark";
import { appUrl, basePath, repoUrl, tagline } from "@/lib/shared";

const PILLARS = [
  {
    title: "Evaluate",
    text: "Any steer, ablation, adapter or retrieval is one Inspect eval, compared to base with paired intervals.",
  },
  {
    title: "Train against",
    text: "SFT, DPO and GRPO on TRL, with the same check as scorer and reward.",
  },
  {
    title: "Look inside",
    text: "Lens, patching, probes and features on the same model, across checkpoints.",
  },
];

const button = "inline-flex h-9 items-center rounded-md px-4 text-sm font-medium transition-colors";

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center px-6 pt-20 pb-16 md:pt-28">
      <Mark className="text-fd-foreground size-12" />
      <h1 className="mt-6 max-w-2xl text-center text-4xl font-semibold tracking-tight text-balance md:text-5xl">
        {tagline}
      </h1>
      <p className="text-fd-muted-foreground mt-4 max-w-xl text-center text-balance">
        An open-source lab where an intervention on a language model is something you evaluate,
        train against and look inside. Local, free, no API keys.
      </p>
      <div className="mt-8">
        <CopyCommand command="pip install loupelab" />
      </div>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Link
          href="/docs"
          className={`${button} bg-fd-primary text-fd-primary-foreground hover:opacity-90`}
        >
          Read the docs
        </Link>
        <a href={repoUrl} className={`${button} hover:bg-fd-accent border`}>
          GitHub
        </a>
        {appUrl ? (
          <a href={appUrl} className={`${button} hover:bg-fd-accent border`}>
            Open the demo
          </a>
        ) : null}
      </div>

      <div className="mt-16 w-full">
        {(["light", "dark"] as const).map((theme) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={theme}
            src={`${basePath}/screenshot-${theme}.png`}
            alt="A grid of conditions against a baseline in the loupe app"
            width={2400}
            height={1500}
            className={`w-full rounded-xl border ${theme === "dark" ? "hidden dark:block" : "dark:hidden"}`}
          />
        ))}
      </div>

      <div className="mt-16 grid w-full gap-8 md:grid-cols-3">
        {PILLARS.map((p) => (
          <div key={p.title}>
            <h2 className="font-medium">{p.title}</h2>
            <p className="text-fd-muted-foreground mt-1 text-sm">{p.text}</p>
          </div>
        ))}
      </div>

      <footer className="text-fd-muted-foreground mt-24 flex gap-4 text-sm">
        <span>Apache 2.0</span>
        <a href={repoUrl} className="hover:text-fd-foreground">
          GitHub
        </a>
        <Link href="/docs" className="hover:text-fd-foreground">
          Docs
        </Link>
      </footer>
    </main>
  );
}
