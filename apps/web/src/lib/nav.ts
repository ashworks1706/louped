import {
  Activity,
  BookOpen,
  Brain,
  Database,
  Dumbbell,
  FlaskConical,
  FileText,
  Gauge,
  GitCompareArrows,
  House,
  LayoutGrid,
  ListTree,
  MessageSquareText,
  Move3d,
  Puzzle,
  Rocket,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

/** Where a page lives in the sidebar: the workspace, or one research domain. */
export type Section = "workspace" | "behavior" | "efficiency";

export type NavItem = {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  shortcut: string;
  section: Section;
};

/** Every page, in sidebar order within its section. The command menu and the sidebar both read
 * this list. */
export const NAV: NavItem[] = [
  {
    href: "/",
    title: "Home",
    description: "What is running and what is being asked.",
    icon: House,
    shortcut: "G H",
    section: "workspace",
  },
  {
    href: "/runs/",
    title: "Runs",
    description: "Every job, eval, analysis and training run, newest first.",
    icon: ListTree,
    shortcut: "G R",
    section: "workspace",
  },
  {
    href: "/compare/",
    title: "Compare",
    description: "Two runs, sample by sample.",
    icon: GitCompareArrows,
    shortcut: "G C",
    section: "workspace",
  },
  {
    href: "/sources/",
    title: "Sources",
    description: "The papers, docs, slides and notebooks the project rests on.",
    icon: BookOpen,
    shortcut: "G S",
    section: "workspace",
  },
  {
    href: "/reports/",
    title: "Reports",
    description: "What the project hands to people: write-ups, decks, documents and figures.",
    icon: FileText,
    shortcut: "G O",
    section: "workspace",
  },
  {
    href: "/launch/",
    title: "Launch",
    description: "Start a script, a config or a command, here or on a cluster.",
    icon: Rocket,
    shortcut: "G L",
    section: "workspace",
  },
  {
    href: "/behavior/",
    title: "Overview",
    description: "What models do, and the mechanisms behind it.",
    icon: LayoutGrid,
    shortcut: "G B",
    section: "behavior",
  },
  {
    href: "/behavior/experiments/",
    title: "Experiments",
    description: "The behavior questions, by domain.",
    icon: FlaskConical,
    shortcut: "G E",
    section: "behavior",
  },
  {
    href: "/behavior/probe/",
    title: "Probe",
    description: "One prompt, with and without an intervention.",
    icon: MessageSquareText,
    shortcut: "G P",
    section: "behavior",
  },
  {
    href: "/behavior/vectors/",
    title: "Vectors",
    description: "Directions in a model's activations that stand for a concept.",
    icon: Move3d,
    shortcut: "G V",
    section: "behavior",
  },
  {
    href: "/behavior/training-sets/",
    title: "Training sets",
    description: "Is a training set sound? Its pairs side by side, with what is wrong flagged.",
    icon: Database,
    shortcut: "G D",
    section: "behavior",
  },
  {
    href: "/behavior/circuits/",
    title: "Circuits",
    description: "Which internal features produce an answer.",
    icon: Waypoints,
    shortcut: "G I",
    section: "behavior",
  },
  {
    href: "/efficiency/",
    title: "Overview",
    description: "What it costs to run a model, and what a change saves.",
    icon: LayoutGrid,
    shortcut: "G F",
    section: "efficiency",
  },
  {
    href: "/efficiency/experiments/",
    title: "Experiments",
    description: "The efficiency questions, by domain.",
    icon: FlaskConical,
    shortcut: "G X",
    section: "efficiency",
  },
  {
    href: "/efficiency/benchmark/",
    title: "Benchmark",
    description: "Latency, throughput and memory of one prompt.",
    icon: Activity,
    shortcut: "G K",
    section: "efficiency",
  },
  {
    href: "/efficiency/training/",
    title: "Training",
    description: "Fine-tuning and adapter runs.",
    icon: Dumbbell,
    shortcut: "G T",
    section: "efficiency",
  },
];

/** The research domains: each a sidebar of its own, entered from the workspace. */
export const DOMAINS: {
  section: Exclude<Section, "workspace">;
  title: string;
  icon: LucideIcon;
}[] = [
  { section: "behavior", title: "Behavior", icon: Brain },
  { section: "efficiency", title: "Efficiency", icon: Gauge },
];

/** The top bar's sections, each opening its sidebar at its first page. */
export const SECTIONS: { section: Section; title: string; href: string }[] = [
  { section: "workspace", title: "Workspace", href: "/" },
  { section: "behavior", title: "Behavior", href: "/behavior/" },
  { section: "efficiency", title: "Efficiency", href: "/efficiency/" },
];

/** Detail pages with no sidebar entry, and the list page that stays highlighted on them. */
const DETAIL: Record<string, string> = {
  "/run/": "/runs/",
  "/job/": "/runs/",
  "/behavior/experiment/": "/behavior/experiments/",
  "/efficiency/experiment/": "/efficiency/experiments/",
  "/behavior/feature/": "/behavior/vectors/",
};

const slash = (path: string) => (path.endsWith("/") ? path : `${path}/`);

/** The section a path belongs to, which picks the sidebar shown: its first segment. */
export function sectionOf(pathname: string): Section {
  const first = slash(pathname).split("/")[1];
  return first === "behavior" || first === "efficiency" ? first : "workspace";
}

/** The sidebar entry a path highlights: its own, or its list page's on a detail page. */
export function activeHref(pathname: string): string | undefined {
  const path = slash(pathname);
  return NAV.find((n) => n.href === path)?.href ?? DETAIL[path];
}

export function navItem(href: string): NavItem {
  const item = NAV.find((n) => n.href === href);
  if (!item) throw new Error(`no nav item for ${href}`);
  return item;
}

/** The title a page shows in the command menu: a domain page carries its domain's name. */
export function fullTitle(item: NavItem): string {
  const domain = DOMAINS.find((d) => d.section === item.section);
  return domain ? `${domain.title} · ${item.title}` : item.title;
}

/** Where a section's plugin pages live: /x/, /behavior/x/, /efficiency/x/, with ?name=. */
export const pluginPath = (section: Section) =>
  section === "workspace" ? "/x/" : `/${section}/x/`;

/** A project plugin's sidebar entry (louped.core.plugins); no G jump, since names are the
 * project's own. */
export function pluginItem(p: {
  name: string;
  title: string;
  description: string;
  section: Section;
}): NavItem {
  return {
    href: `${pluginPath(p.section)}?name=${encodeURIComponent(p.name)}`,
    title: p.title,
    description: p.description,
    icon: Puzzle,
    shortcut: "",
    section: p.section,
  };
}
