"use client";

import { useQuery } from "@tanstack/react-query";
import { FolderKanban, Menu, PanelLeftClose, PanelLeftOpen, Rocket, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { useCommandMenu } from "@/components/command-menu";
import { useLive } from "@/components/home-overview";
import { Mark } from "@/components/mark";
import { Cues } from "@/components/cues";
import { arrange, part, partId, useRules } from "@/components/parts";
import { NoteMarks } from "@/components/notes";
import { PartPicker } from "@/components/pick-parts";
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
import { NativeSelect } from "@/components/ui/native-select";
import { projectHref } from "@/lib/href";
import {
  activeHref,
  BOARD_PATH,
  boardItem,
  GROUPS,
  NAV,
  PLUGIN_PATH,
  pluginItem,
  type NavItem,
} from "@/lib/nav";
import { scoped, useProject } from "@/lib/scope";
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

/** The top bar (search, Launch, what is running) over the sidebar: the project, then every page. */
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
      {/* outside the top bar: its backdrop blur would hold fixed children to it */}
      <Suspense>
        <NoteMarks />
        <PartPicker />
        <Cues />
      </Suspense>
    </div>
  );
}

function TopBar({ folded, toggle }: { folded: boolean; toggle: () => void }) {
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
        {...part("shell/sidebar")}
      >
        {folded ? <PanelLeftOpen /> : <PanelLeftClose />}
      </Button>
      <Scoped href="/">
        {(href) => (
          <Link
            href={href}
            className="flex items-center gap-2 pr-2 text-sm font-semibold tracking-tight"
            {...part("shell/home")}
          >
            <Mark className="size-5" />
            louped
          </Link>
        )}
      </Scoped>
      <div className="ml-auto flex items-center gap-2">
        <span {...part("shell/jobs")} className="contents">
          <LiveJobs />
        </span>
        <SearchButton />
        <Scoped href="/launch/">
          {(href) => (
            <Button asChild size="sm" variant="outline" {...part("shell/launch")}>
              <Link href={href} aria-label="Launch">
                <Rocket />
                <span className="hidden sm:inline">Launch</span>
              </Link>
            </Button>
          )}
        </Scoped>
        <span className="hidden lg:block" {...part("shell/status")}>
          <ServerStatus />
        </span>
        <span {...part("shell/theme")}>
          <ThemeToggle />
        </span>
      </div>
    </header>
  );
}

/** A link in the picked project's scope; unscoped while the address is read (a static page reads
 * it under Suspense). */
function Scoped({ href, children }: { href: string; children: (href: string) => React.ReactNode }) {
  return (
    <Suspense fallback={children(href)}>
      <InScope href={href}>{children}</InScope>
    </Suspense>
  );
}

function InScope({
  href,
  children,
}: {
  href: string;
  children: (href: string) => React.ReactNode;
}) {
  const [project] = useProject();
  return children(scoped(href, project));
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
      {...part("shell/search")}
    >
      <Search className="size-3.5" />
      <span className="hidden sm:inline">Search</span>
      <Kbd className="ml-auto hidden sm:inline-flex">⌘K</Kbd>
    </button>
  );
}

/** The project switcher, then each group's pages; folded, their icons with the name on hover. */
function SidebarNav(props: { folded?: boolean; onNavigate?: () => void }) {
  return (
    <Suspense fallback={<SidebarBody {...props} project={null} />}>
      <ScopedSidebar {...props} />
    </Suspense>
  );
}

function ScopedSidebar(props: { folded?: boolean; onNavigate?: () => void }) {
  const [project] = useProject();
  return <SidebarBody {...props} project={project} />;
}

function SidebarBody({
  folded = false,
  onNavigate,
  project,
}: {
  folded?: boolean;
  onNavigate?: () => void;
  project: string | null;
}) {
  const pathname = usePathname();
  const active = activeHref(pathname);
  const rule = useRules();
  const items = arrange(NAV, (n) => partId("shell/nav", n.href), rule);
  const health = useQuery(q.health());
  return (
    <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2" aria-label="Pages">
      <Suspense>
        <ProjectSwitcher folded={folded} onNavigate={onNavigate} />
      </Suspense>
      {GROUPS.map((g) => (
        <div
          key={g.group}
          className="flex flex-col gap-0.5"
          {...part(partId("shell/group", g.group))}
        >
          {folded ? (
            <span className="bg-border mx-auto my-1.5 h-px w-6" aria-hidden />
          ) : (
            <p className="text-muted-foreground flex h-8 items-end px-2 pb-1 text-xs font-medium">
              {rule(partId("shell/group", g.group)).label ?? g.title}
            </p>
          )}
          {items
            .filter((n) => n.group === g.group)
            .map((item) => (
              <NavLink
                key={item.href}
                item={{
                  ...item,
                  // the overview of a project is its page
                  href:
                    item.href === "/" && project
                      ? projectHref(project)
                      : scoped(item.href, project),
                  title: rule(partId("shell/nav", item.href)).label ?? item.title,
                }}
                address={item.href}
                active={item.href === active}
                folded={folded}
                onNavigate={onNavigate}
              />
            ))}
          {g.group === "research" && (
            <Suspense>
              <BoardLinks folded={folded} onNavigate={onNavigate} />
              <PluginLinks folded={folded} onNavigate={onNavigate} />
            </Suspense>
          )}
        </div>
      ))}
      <div className="mt-auto flex flex-col gap-0.5 pt-4" {...part(partId("shell/group", "app"))}>
        {items
          // a shared server or a published dashboard keeps no requests
          .filter((n) => n.group === "app" && health.data?.launching)
          .map((item) => (
            <NavLink
              key={item.href}
              item={{ ...item, title: rule(partId("shell/nav", item.href)).label ?? item.title }}
              address={item.href}
              active={item.href === active}
              folded={folded}
              onNavigate={onNavigate}
            />
          ))}
      </div>
    </nav>
  );
}

/** Which project the app is scoped to: every list then shows that project's part. */
function ProjectSwitcher({ folded, onNavigate }: { folded: boolean; onNavigate?: () => void }) {
  const projects = useQuery(q.projects());
  const [project, setProject] = useProject();
  const pathname = usePathname();
  const rule = useRules()("shell/project");
  if (rule.hidden) return null;
  const all = projects.data ?? [];
  const manage = (
    <Link
      href="/projects/"
      onClick={onNavigate}
      aria-label="All projects"
      title="All projects"
      aria-current={pathname.startsWith("/projects/") && !project ? "page" : undefined}
      className={cn(
        "text-muted-foreground hover:bg-accent/60 hover:text-foreground flex size-8 shrink-0 items-center justify-center rounded-md transition-colors",
        folded && "mx-auto",
      )}
      {...part("shell/projects")}
    >
      <FolderKanban className="size-4" />
    </Link>
  );
  if (folded) return manage;
  return (
    <div className="flex items-center gap-1 pb-1" {...part("shell/project")}>
      <NativeSelect
        aria-label="Project"
        value={project ?? ""}
        onChange={(e) => void setProject(e.target.value || null)}
        className="h-8 min-w-0 flex-1 text-sm"
      >
        <option value="">{rule.label ?? "All projects"}</option>
        {[...new Set([...all.map((p) => p.name), ...(project ? [project] : [])])].map((name) => (
          <option key={name} value={name}>
            {all.find((p) => p.name === name)?.title ?? name}
          </option>
        ))}
      </NativeSelect>
      {manage}
    </div>
  );
}

/** The project's boards shown as pages: boards/<name>.json, one entry each. */
function BoardLinks({ folded, onNavigate }: { folded: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const name = useSearchParams().get("name");
  const boards = useQuery(q.boards());
  const here = pathname.replace(/\/?$/, "/") === BOARD_PATH;
  return (boards.data ?? [])
    .map(boardItem)
    .map((b) => (
      <NavLink
        key={b.href}
        item={b}
        active={here && b.href.endsWith(`?name=${encodeURIComponent(name ?? "")}`)}
        folded={folded}
        onNavigate={onNavigate}
      />
    ));
}

/** The project's plugins with a page: louped.core.plugins, one entry each. */
function PluginLinks({ folded, onNavigate }: { folded: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const name = useSearchParams().get("name");
  const plugins = useQuery(q.plugins());
  const here = pathname.replace(/\/?$/, "/") === PLUGIN_PATH;
  return (plugins.data ?? []).map((p) => (
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
  address = item.href,
  active,
  folded,
  onNavigate,
}: {
  item: NavItem;
  /** The part address: the page's own href, without the project scope. */
  address?: string;
  active: boolean;
  folded: boolean;
  onNavigate?: () => void;
}) {
  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      {...part(partId("shell/nav", address))}
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

/** On a phone: the sidebar, in a sheet. */
function MobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Menu"
          className="md:hidden"
          {...part("shell/menu")}
        >
          <Menu />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64 p-3">
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <SheetDescription className="sr-only">The project and its pages.</SheetDescription>
        <div className="mt-8 flex flex-col gap-4">
          <SidebarNav onNavigate={() => setOpen(false)} />
          <ServerStatus />
        </div>
      </SheetContent>
    </Sheet>
  );
}
