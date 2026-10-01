"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCommandMenu } from "@/components/command-menu";
import { useLive } from "@/components/home-overview";
import { Mark } from "@/components/mark";
import { ServerStatus } from "@/components/server-status";
import { ThemeToggle } from "@/components/theme-toggle";
import { Kbd } from "@/components/ui/kbd";
import { NAV } from "@/lib/nav";
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

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <>
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r md:flex">
        <div className="flex h-14 items-center px-4">
          <Wordmark />
        </div>
        <div className="px-3">
          <SearchButton className="w-full" />
        </div>
        <nav className="mt-4 flex flex-col gap-0.5 px-3" aria-label="Main">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
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
          })}
        </nav>
        <div className="mt-auto flex items-center justify-between border-t px-4 py-3">
          <ServerStatus />
          <ThemeToggle />
        </div>
      </aside>
      <header className="bg-background/80 sticky top-0 z-40 flex h-14 items-center gap-3 border-b px-4 backdrop-blur md:hidden">
        <Wordmark />
        <SearchButton className="ml-auto w-36" />
        <ThemeToggle />
      </header>
    </>
  );
}
