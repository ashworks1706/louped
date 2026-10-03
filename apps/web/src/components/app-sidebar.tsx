"use client";

import { ChevronLeft, ChevronRight, Menu, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

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
import { DOMAINS, NAV, sectionOf, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

/** A list page stays highlighted on its detail page: /runs/ on /run/, /experiments/ on
 * /experiment/. */
function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href.replace(/s?\/$/, ""));
}

/** How many are running behind a page: jobs behind Launch, runs behind Runs. */
function LiveCount({ href }: { href: string }) {
  const live = useLive();
  const n = href === "/launch/" ? live.jobs.length : href === "/runs/" ? live.runs.length : 0;
  if (n === 0) return null;
  return (
    <span
      className="text-foreground ml-auto inline-flex items-center gap-1.5 font-mono text-[11px] tabular-nums"
      aria-label={`${n} running`}
    >
      <span className="bg-foreground size-1.5 rounded-full motion-safe:animate-pulse" />
      {n}
    </span>
  );
}

function Wordmark() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <Mark className="size-6" />
      loupe
    </Link>
  );
}

function SearchButton({ className }: { className?: string }) {
  const setOpen = useCommandMenu();
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className={cn(
        "bg-background text-muted-foreground hover:bg-accent flex h-8 items-center gap-2 rounded-md border px-2 text-sm transition-colors",
        className,
      )}
    >
      <Search className="size-3.5" />
      <span>Search</span>
      <Kbd className="ml-auto">⌘K</Kbd>
    </button>
  );
}

/** The pages of the current section. In the workspace, the domains follow, each opening its own
 * sidebar; in a domain, a way back comes first. */
function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const section = sectionOf(pathname);
  const domain = DOMAINS.find((d) => d.section === section);
  const items = NAV.filter((n) => n.section === section);
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {domain && (
        <>
          <Link
            href="/"
            onClick={onNavigate}
            className="text-muted-foreground hover:text-foreground flex h-8 items-center gap-1.5 rounded-md px-2 text-xs transition-colors"
          >
            <ChevronLeft className="size-3.5" />
            Workspace
          </Link>
          <p className="flex h-8 items-center gap-2 px-2 text-sm font-semibold">
            <domain.icon className="size-4" />
            {domain.title}
          </p>
        </>
      )}
      {items.map((item) => (
        <NavLink
          key={item.href}
          item={item}
          active={isActive(pathname, item.href)}
          onNavigate={onNavigate}
        />
      ))}
      {!domain && (
        <>
          <p className="text-muted-foreground mt-5 mb-1 px-2 text-xs font-medium">Domains</p>
          {DOMAINS.map((d) => {
            const first = NAV.find((n) => n.section === d.section);
            if (!first) return null;
            return (
              <Link
                key={d.section}
                href={first.href}
                onClick={onNavigate}
                className="text-muted-foreground hover:bg-accent/60 hover:text-foreground flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors"
              >
                <d.icon className="size-4" />
                {d.title}
                <ChevronRight className="ml-auto size-3.5" />
              </Link>
            );
          })}
        </>
      )}
    </nav>
  );
}

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors",
        active
          ? "bg-accent text-foreground font-medium"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
      )}
    >
      <item.icon className="size-4" />
      {item.title}
      <LiveCount href={item.href} />
    </Link>
  );
}

/** On a phone, the same navigation in a sheet from the menu button. */
function MobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Menu">
          <Menu />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64 p-3">
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <SheetDescription className="sr-only">Pages of this section.</SheetDescription>
        <div className="mt-8">
          <SidebarNav onNavigate={() => setOpen(false)} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function AppSidebar() {
  return (
    <>
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r md:flex">
        <div className="flex h-14 items-center px-4">
          <Wordmark />
        </div>
        <div className="px-3">
          <SearchButton className="w-full" />
        </div>
        <div className="mt-4 px-3">
          <SidebarNav />
        </div>
        <div className="mt-auto flex items-center justify-between border-t px-4 py-3">
          <ServerStatus />
          <ThemeToggle />
        </div>
      </aside>
      <header className="bg-background/80 sticky top-0 z-40 flex h-14 items-center gap-2 border-b px-4 backdrop-blur md:hidden">
        <MobileNav />
        <Wordmark />
        <SearchButton className="ml-auto w-36" />
        <ThemeToggle />
      </header>
    </>
  );
}
