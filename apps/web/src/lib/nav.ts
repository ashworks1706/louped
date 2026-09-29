import {
  FlaskConical,
  GitCompareArrows,
  House,
  ListTree,
  MessageSquareText,
  Move3d,
  Rocket,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  shortcut: string;
};

/** Every page, in sidebar order. The command menu and the sidebar both read this list. */
export const NAV: NavItem[] = [
  {
    href: "/",
    title: "Home",
    description: "Latest runs.",
    icon: House,
    shortcut: "G H",
  },
  {
    href: "/experiments/",
    title: "Experiments",
    description: "Research questions and their runs.",
    icon: FlaskConical,
    shortcut: "G E",
  },
  {
    href: "/launch/",
    title: "Launch",
    description: "Run an experiment, training config or eval, and follow it.",
    icon: Rocket,
    shortcut: "G L",
  },
  {
    href: "/runs/",
    title: "Runs",
    description: "Evals, analyses and training.",
    icon: ListTree,
    shortcut: "G R",
  },
  {
    href: "/compare/",
    title: "Compare",
    description: "Two runs, sample by sample.",
    icon: GitCompareArrows,
    shortcut: "G C",
  },
  {
    href: "/vectors/",
    title: "Vectors",
    description: "Saved directions.",
    icon: Move3d,
    shortcut: "G V",
  },
  {
    href: "/circuits/",
    title: "Circuits",
    description: "Attribution graphs from circuit-tracer.",
    icon: Waypoints,
    shortcut: "G I",
  },
  {
    href: "/playground/",
    title: "Playground",
    description: "A prompt, with and without an intervention.",
    icon: MessageSquareText,
    shortcut: "G P",
  },
];

export function navItem(href: string): NavItem {
  const item = NAV.find((n) => n.href === href);
  if (!item) throw new Error(`no nav item for ${href}`);
  return item;
}
