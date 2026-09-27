import Image from "next/image";
import Link from "next/link";

import { CopyCommand } from "@/components/copy-command";
import { docsRoute, repoUrl, tagline } from "@/lib/shared";

import dark from "../../../public/screenshot-dark.png";
import light from "../../../public/screenshot-light.png";

const PILLARS = [
  { title: "Evaluate", text: "Every steer, ablation or adapter is an Inspect eval against base." },
  { title: "Train against", text: "SFT, DPO and GRPO with the same check as reward." },
  { title: "Look inside", text: "Lens, patching and probes across checkpoints." },
];

const alt = "A grid of conditions against a baseline in the loupe app";

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center px-6 pt-24 pb-16 md:pt-32">
      <h1 className="max-w-2xl text-center text-4xl font-semibold tracking-tight text-balance md:text-6xl">
        {tagline}
      </h1>
      <p className="text-fd-muted-foreground mt-5 max-w-md text-center text-balance">
        Evaluate, train and interpret language model interventions. Local and free.
      </p>
      <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
        <CopyCommand command="pip install loupelab" />
        <Link
          href={docsRoute}
          className="bg-fd-primary text-fd-primary-foreground inline-flex h-10.5 items-center rounded-lg px-5 text-sm font-medium hover:opacity-90"
        >
          Get started
        </Link>
      </div>

      <div className="mt-20 w-full overflow-hidden rounded-xl border shadow-2xl shadow-black/5">
        <Image src={light} alt={alt} priority className="dark:hidden" />
        <Image src={dark} alt={alt} priority className="hidden dark:block" />
      </div>

      <div className="mt-20 grid w-full gap-10 md:grid-cols-3">
        {PILLARS.map((p) => (
          <div key={p.title}>
            <h2 className="text-sm font-medium">{p.title}</h2>
            <p className="text-fd-muted-foreground mt-1 text-sm">{p.text}</p>
          </div>
        ))}
      </div>

      <footer className="text-fd-muted-foreground mt-32 flex w-full justify-between border-t pt-6 text-sm">
        <span>Apache 2.0</span>
        <a href={repoUrl} className="hover:text-fd-foreground">
          GitHub
        </a>
      </footer>
    </main>
  );
}
