"use client";

import { useQuery } from "@tanstack/react-query";
import { Menu, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { useCommandMenu } from "@/components/command-menu";
import { useLive } from "@/components/home-overview";
import { Mark } from "@/components/mark";
import { ServerStatus } from "@/components/server-status";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { q } from "@/lib/api";
import {
  activeHref,
  DOMAINS,
  NAV,
  pluginItem,
  pluginPath,
  SECTIONS,
  sectionOf,
  type NavItem,
} from "@/lib/nav";
import { cn } from "@/lib/utils";

/** Whether the sidebar is folded to icons: this viewer's choice, kept in the browser when it
 * allows, else for this page only. */
const FOLD_KEY = "louped.sidebar.folded";
let foldedHere = false;
const foldListeners = new Set<() => void>();

function readFolded() {
  try {
    const stored = localStorage.getItem(FOLD_KEY);
    return stored == null ? foldedHere : stored === "1";
  } catch {
    return foldedHere;
  }
}

function useFolded(): [boolean, () => void] {
  const folded = useSyncExternalStore(
    (notify) => {
      foldListeners.add(notify);
      return () => foldListeners.delete(notify);
    },
    readFolded,
    () => false,
  );
  const toggle = useCallback(() => {
    foldedHere = !readFolded();
    try {
      localStorage.setItem(FOLD_KEY, foldedHere ? "1" : "0");
    } catch {
      // storage blocked: the choice lasts this page only
    }
    foldListeners.forEach((notify) => notify());
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggle();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggle]);
  return [folded, toggle];
}

/** The top bar (sections, search, what is running) over a sidebar of the section's pages. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [folded, toggle] = useFolded();
  return (
    <div className="flex min-h-dvh flex-col">
      <TopBar folded={folded} toggle={toggle} />
      <div className="flex flex-1">
        <aside
          className={cn(
            "sticky top-12 hidden h-[calc(100dvh-3rem)] shrink-0 flex-col border-r transition-[width] duration-150 md:flex",
            folded ? "w-14" : "w-56",
          )}
        >
          <SidebarNav folded={folded} />
        </aside>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

function TopBar({ folded, toggle }: { folded: boolean; toggle: () => void }) {
  const pathname = usePathname();
  const section = sectionOf(pathname);
  return (
    <header className="bg-background/80 sticky top-0 z-40 flex h-12 items-center gap-2 border-b px-3 backdrop-blur">
      <MobileNav />
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={toggle}
        aria-label={folded ? "Expand sidebar" : "Collapse sidebar"}
        title={folded ? "Expand sidebar (⌘B)" : "Collapse sidebar (⌘B)"}
        className="hidden md:inline-flex"
      >
        {folded ? <PanelLeftOpen /> : <PanelLeftClose />}
      </Button>
      <Link href="/" className="flex items-center gap-2 pr-2 text-sm font-semibold tracking-tight">
        <Mark className="size-5" />
        louped
      </Link>
      <nav aria-label="Sections" className="hidden items-center gap-0.5 sm:flex">
        {SECTIONS.map((s) => (
          <Link
            key={s.section}
            href={s.href}
            aria-current={s.section === section ? "page" : undefined}
            className={cn(
              "flex h-8 items-center rounded-md px-3 text-sm transition-colors",
              s.section === section
                ? "bg-accent text-foreground font-medium"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {s.title}
          </Link>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <LiveJobs />
        <SearchButton />
        <span className="hidden lg:block">
          <ServerStatus />
        </span>
        <ThemeToggle />
      </div>
    </header>
  );
}

/** What is running, a click from the Runs page that follows it. */
function LiveJobs() {
  const live = useLive();
  const n = live.jobs.length + live.runs.length;
  if (n === 0) return null;
  return (
    <Link
      href="/runs/"
      className="hover:bg-accent flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs transition-colors"
    >
      <span className="bg-foreground size-1.5 rounded-full motion-safe:animate-pulse" />
      <span className="font-mono tabular-nums">{n}</span> running
    </Link>
  );
}

function SearchButton() {
  const setOpen = useCommandMenu();
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className="bg-background text-muted-foreground hover:bg-accent flex h-8 items-center gap-2 rounded-md border px-2 text-sm transition-colors sm:w-48"
      aria-label="Search"
    >
      <Search className="size-3.5" />
      <span className="hidden sm:inline">Search</span>
      <Kbd className="ml-auto hidden sm:inline-flex">⌘K</Kbd>
    </button>
  );
}

/** The current section's pages; folded, their icons with the name on hover. */
function SidebarNav({ folded = false, onNavigate }: { folded?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const section = sectionOf(pathname);
  const domain = DOMAINS.find((d) => d.section === section);
  const active = activeHref(pathname);
  const items = NAV.filter((n) => n.section === section);
  return (
    <nav className="flex flex-col gap-0.5 p-2" aria-label="Pages">
      {!folded && (
        <p className="text-muted-foreground flex h-8 items-center gap-2 px-2 text-xs font-medium">
          {domain ? (
            <>
              <domain.icon className="size-3.5" />
              {domain.title}
            </>
          ) : (
            "Workspace"
          )}
        </p>
      )}
      {items.map((item) => (
        <NavLink
          key={item.href}
          item={item}
          active={item.href === active}
          folded={folded}
          onNavigate={onNavigate}
        />
      ))}
      <Suspense>
        <PluginLinks folded={folded} onNavigate={onNavigate} />
      </Suspense>
    </nav>
  );
}

/** The project's plugins in this section: louped.core.plugins, one entry each. */
function PluginLinks({ folded, onNavigate }: { folded: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const name = useSearchParams().get("name");
  const section = sectionOf(pathname);
  const plugins = useQuery(q.plugins());
  const here = pathname.replace(/\/?$/, "/") === pluginPath(section);
  return (plugins.data ?? [])
    .filter((p) => p.section === section)
    .map((p) => (
      <NavLink
        key={p.name}
        item={pluginItem(p)}
        active={here && name === p.name}
        folded={folded}
        onNavigate={onNavigate}
      />
    ));
}

function NavLink({
  item,
  active,
  folded,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  folded: boolean;
  onNavigate?: () => void;
}) {
  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      aria-label={folded ? item.title : undefined}
      className={cn(
        "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors",
        folded && "justify-center px-0",
        active
          ? "bg-accent text-foreground font-medium"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
      )}
    >
      <item.icon className="size-4 shrink-0" />
      {!folded && item.title}
    </Link>
  );
  if (!folded) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{item.title}</TooltipContent>
    </Tooltip>
  );
}

/** On a phone: the sections and the current section's pages, in a sheet. */
function MobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const section = sectionOf(pathname);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Menu" className="md:hidden">
          <Menu />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64 p-3">
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <SheetDescription className="sr-only">Sections and their pages.</SheetDescription>
        <div className="mt-8 flex flex-col gap-4">
          <div className="flex flex-col gap-0.5">
            {SECTIONS.map((s) => (
              <Link
                key={s.section}
                href={s.href}
                onClick={() => setOpen(false)}
                className={cn(
                  "flex h-8 items-center rounded-md px-2 text-sm",
                  s.section === section ? "bg-accent font-medium" : "text-muted-foreground",
                )}
              >
                {s.title}
              </Link>
            ))}
          </div>
          <div className="border-t pt-2">
            <SidebarNav onNavigate={() => setOpen(false)} />
          </div>
          <ServerStatus />
        </div>
      </SheetContent>
    </Sheet>
  );
}
