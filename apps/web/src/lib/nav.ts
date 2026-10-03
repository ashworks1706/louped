import {
  Activity,
  Brain,
  Dumbbell,
  FlaskConical,
  Gauge,
  GitCompareArrows,
  House,
  LayoutGrid,
  ListTree,
  MessageSquareText,
  Move3d,
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
    href: "/experiments/",
    title: "Experiments",
    description: "Every research question, by domain.",
    icon: FlaskConical,
    shortcut: "G E",
    section: "workspace",
  },
  {
    href: "/runs/",
    title: "Runs",
    description: "Every eval, analysis and training run.",
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
    href: "/launch/",
    title: "Launch",
    description: "Start a run and follow it.",
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
    href: "/playground/",
    title: "Probe",
    description: "One prompt, with and without an intervention.",
    icon: MessageSquareText,
    shortcut: "G P",
    section: "behavior",
  },
  {
    href: "/vectors/",
    title: "Vectors",
    description: "Directions in a model's activations that stand for a concept.",
    icon: Move3d,
    shortcut: "G V",
    section: "behavior",
  },
  {
    href: "/circuits/",
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
    href: "/benchmark/",
    title: "Benchmark",
    description: "Latency, throughput and memory of one prompt.",
    icon: Activity,
    shortcut: "G K",
    section: "efficiency",
  },
  {
    href: "/training/",
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

/** Detail pages with no sidebar entry, filed under the section of the list they belong to. */
const DETAIL: Record<string, Section> = {
  "/feature/": "behavior",
  "/run/": "workspace",
  "/experiment/": "workspace",
};

/** The section a path belongs to, which picks the sidebar shown. */
export function sectionOf(pathname: string): Section {
  const path = pathname.endsWith("/") ? pathname : `${pathname}/`;
  return NAV.find((n) => n.href !== "/" && path === n.href)?.section ?? DETAIL[path] ?? "workspace";
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
