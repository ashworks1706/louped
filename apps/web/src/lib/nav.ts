import {
  Activity,
  BookOpen,
  Boxes,
  Brain,
  Database,
  FileText,
  FlaskConical,
  FolderKanban,
  Gauge,
  GitCompareArrows,
  House,
  LayoutDashboard,
  Lightbulb,
  ListTree,
  MessageSquareText,
  Move3d,
  Puzzle,
  Rocket,
  StickyNote,
  Table2,
  Trophy,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

/** The sidebar's groups: the research (questions, runs, write-ups), the instruments (one prompt,
 * live) and the data; at its foot, louped itself (Feedback). Launch and Projects have no sidebar
 * entry: the top bar's Launch button and the project switcher open them. */
export type Group = "research" | "instruments" | "data" | "app" | "hidden";

/** Behavior or efficiency: an experiment's axis, a filter on lists, not a place in the app. */
export type Axis = "behavior" | "efficiency";

export type NavItem = {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  shortcut: string;
  group: Group;
};

/** Every page, in sidebar order within its group. The command menu and the sidebar both read
 * this list. */
export const NAV: NavItem[] = [
  {
    href: "/",
    title: "Overview",
    description: "What is running and what is being asked.",
    icon: House,
    shortcut: "G H",
    group: "research",
  },
  {
    href: "/experiments/",
    title: "Experiments",
    description: "The questions, by domain.",
    icon: FlaskConical,
    shortcut: "G E",
    group: "research",
  },
  {
    href: "/runs/",
    title: "Runs",
    description: "Every job, eval, analysis and training run, newest first.",
    icon: ListTree,
    shortcut: "G R",
    group: "research",
  },
  {
    href: "/compare/",
    title: "Compare",
    description: "Two runs, sample by sample.",
    icon: GitCompareArrows,
    shortcut: "G C",
    group: "research",
  },
  {
    href: "/reports/",
    title: "Reports",
    description: "What the project hands to people: write-ups, decks, documents and figures.",
    icon: FileText,
    shortcut: "G O",
    group: "research",
  },
  {
    href: "/notes/",
    title: "Notes",
    description: "What you and your agent noted on runs, rows and figures.",
    icon: StickyNote,
    shortcut: "G N",
    group: "research",
  },
  {
    href: "/probe/",
    title: "Probe",
    description: "One prompt, with and without an intervention.",
    icon: MessageSquareText,
    shortcut: "G P",
    group: "instruments",
  },
  {
    href: "/circuits/",
    title: "Circuits",
    description: "Which internal features produce an answer.",
    icon: Waypoints,
    shortcut: "G I",
    group: "instruments",
  },
  {
    href: "/vectors/",
    title: "Vectors",
    description: "Directions in a model's activations that stand for a concept.",
    icon: Move3d,
    shortcut: "G V",
    group: "instruments",
  },
  {
    href: "/speed/",
    title: "Speed",
    description: "Latency, throughput and memory of one prompt.",
    icon: Activity,
    shortcut: "G K",
    group: "instruments",
  },
  {
    href: "/datasets/",
    title: "Datasets",
    description: "What data does the project use? Its Hub datasets, files and training sets.",
    icon: Table2,
    shortcut: "G A",
    group: "data",
  },
  {
    href: "/benchmarks/",
    title: "Benchmarks",
    description: "Which model scores best on each eval task, and which runs fastest?",
    icon: Trophy,
    shortcut: "G M",
    group: "data",
  },
  {
    href: "/training-sets/",
    title: "Training sets",
    description: "Is a training set sound? Its pairs side by side, with what is wrong flagged.",
    icon: Database,
    shortcut: "G D",
    group: "data",
  },
  {
    href: "/sources/",
    title: "Sources",
    description: "The papers, docs, slides and notebooks the project rests on.",
    icon: BookOpen,
    shortcut: "G S",
    group: "data",
  },
  {
    href: "/hub/",
    title: "Hub",
    description: "Models, embeddings, datasets and papers on Hugging Face, added to the project.",
    icon: Boxes,
    shortcut: "G U",
    group: "data",
  },
  {
    href: "/feedback/",
    title: "Feedback",
    description: "What louped lacks or gets wrong, drafted here and filed on GitHub.",
    icon: Lightbulb,
    shortcut: "G F",
    group: "app",
  },
  {
    href: "/projects/",
    title: "Projects",
    description: "The goals the experiments serve, each with its README, links and runs.",
    icon: FolderKanban,
    shortcut: "G J",
    group: "hidden",
  },
  {
    href: "/launch/",
    title: "Launch",
    description: "Start a script, a config or a command, here or on a cluster.",
    icon: Rocket,
    shortcut: "G L",
    group: "hidden",
  },
];

/** The sidebar's groups in order, with their headings. */
export const GROUPS: { group: Exclude<Group, "app" | "hidden">; title: string }[] = [
  { group: "research", title: "Research" },
  { group: "instruments", title: "Instruments" },
  { group: "data", title: "Data" },
];

export const AXES: { axis: Axis; title: string; icon: LucideIcon }[] = [
  { axis: "behavior", title: "Behavior", icon: Brain },
  { axis: "efficiency", title: "Efficiency", icon: Gauge },
];

/** Detail pages with no sidebar entry, and the list page that stays highlighted on them. */
const DETAIL: Record<string, string> = {
  "/run/": "/runs/",
  "/job/": "/runs/",
  "/projects/": "/",
  "/projects/p/": "/",
  "/experiment/": "/experiments/",
  "/feature/": "/vectors/",
};

const slash = (path: string) => (path.endsWith("/") ? path : `${path}/`);

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

/** Where a project's plugin pages live, with ?name=. */
export const PLUGIN_PATH = "/x/";

/** A project plugin's sidebar entry (louped.core.plugins); no G jump, since names are the
 * project's own. */
export function pluginItem(p: { name: string; title: string; description: string }): NavItem {
  return {
    href: `${PLUGIN_PATH}?name=${encodeURIComponent(p.name)}`,
    title: p.title,
    description: p.description,
    icon: Puzzle,
    shortcut: "",
    group: "research",
  };
}

/** Where boards shown as pages live, with ?name=. */
export const BOARD_PATH = "/b/";

/** A board's sidebar entry (boards/<name>.json); no G jump, since names are the project's own. */
export function boardItem(b: { name: string; title: string; about?: string | null }): NavItem {
  return {
    href: `${BOARD_PATH}?name=${encodeURIComponent(b.name)}`,
    title: b.title,
    description: b.about ?? "A board the project's agent made.",
    icon: LayoutDashboard,
    shortcut: "",
    group: "research",
  };
}

/** Pages the app had under /behavior/ and /efficiency/, and where each is now. Old links, published
 * dashboards and agents' notes keep working through these. */
export const MOVED: Record<string, string> = {
  "/behavior/": "/experiments/?axis=behavior",
  "/efficiency/": "/experiments/?axis=efficiency",
  "/behavior/experiments/": "/experiments/?axis=behavior",
  "/efficiency/experiments/": "/experiments/?axis=efficiency",
  "/behavior/experiment/": "/experiment/",
  "/efficiency/experiment/": "/experiment/",
  "/behavior/probe/": "/probe/",
  "/behavior/circuits/": "/circuits/",
  "/behavior/vectors/": "/vectors/",
  "/behavior/feature/": "/feature/",
  "/behavior/training-sets/": "/training-sets/",
  "/behavior/training/": "/runs/?kind=training",
  "/efficiency/training/": "/runs/?kind=training",
  "/behavior/datasets/": "/datasets/?axis=behavior",
  "/efficiency/datasets/": "/datasets/?axis=efficiency",
  "/behavior/benchmarks/": "/benchmarks/?axis=behavior",
  "/efficiency/benchmarks/": "/benchmarks/?axis=efficiency",
  "/efficiency/benchmark/": "/speed/",
  "/behavior/b/": "/b/",
  "/efficiency/b/": "/b/",
  "/behavior/x/": "/x/",
  "/efficiency/x/": "/x/",
};
