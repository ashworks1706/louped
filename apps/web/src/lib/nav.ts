import {
  FlaskConical,
  GitCompareArrows,
  House,
  ListTree,
  MessageSquareText,
  Move3d,
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
    description: "Recent runs and where to start.",
    icon: House,
    shortcut: "G H",
  },
  {
    href: "/experiments/",
    title: "Experiments",
    description: "One card per research question, with the runs that answer it.",
    icon: FlaskConical,
    shortcut: "G E",
  },
  {
    href: "/runs/",
    title: "Runs",
    description: "Every run: evals, analyses and training, filterable and comparable.",
    icon: ListTree,
    shortcut: "G R",
  },
  {
    href: "/compare/",
    title: "Compare",
    description: "Runs or policies side by side, aligned by sample.",
    icon: GitCompareArrows,
    shortcut: "G C",
  },
  {
    href: "/vectors/",
    title: "Vectors",
    description: "Saved directions: where they came from and what they do.",
    icon: Move3d,
    shortcut: "G V",
  },
  {
    href: "/playground/",
    title: "Playground",
    description: "Chat with a model, with and without an intervention, side by side.",
    icon: MessageSquareText,
    shortcut: "G P",
  },
];

export function navItem(href: string): NavItem {
  const item = NAV.find((n) => n.href === href);
  if (!item) throw new Error(`no nav item for ${href}`);
  return item;
}
