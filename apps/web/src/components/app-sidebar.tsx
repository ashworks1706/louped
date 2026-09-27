"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCommandMenu } from "@/components/command-menu";
import { ServerStatus } from "@/components/server-status";
import { ThemeToggle } from "@/components/theme-toggle";
import { Kbd } from "@/components/ui/kbd";
import { NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href.replace(/\/$/, ""));
}

function Wordmark() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="border-foreground grid size-6 place-items-center rounded-full border-2">
        <span className="bg-foreground size-2 rounded-full" />
      </span>
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
