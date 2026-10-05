"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Crosshair, FlaskConical, Moon } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import * as React from "react";

import { setTapping, useCanPick } from "@/components/pick-parts";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { q } from "@/lib/api";
import { experimentHref } from "@/lib/href";
import { fullTitle, NAV, pluginItem } from "@/lib/nav";

const DOCS = "https://github.com/ashworks1706/louped/tree/main/docs";

const CommandMenuContext = React.createContext<(open: boolean) => void>(() => {});

/** Opens the command menu from anywhere, e.g. the search button in the sidebar. */
export const useCommandMenu = () => React.useContext(CommandMenuContext);

function typingInField(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

/** ⌘K for everything, plus two-key "G then letter" jumps to each page. */
export function CommandMenu({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  // Fetched only once the menu opens, so a page that never opens it pays nothing.
  const experiments = useQuery({ ...q.experiments(), enabled: open });
  const plugins = useQuery({ ...q.plugins(), enabled: open });
  const canPick = useCanPick();

  React.useEffect(() => {
    let leader = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (open || typingInField(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toUpperCase();
      if (leader) {
        leader = false;
        const item = NAV.find((n) => n.shortcut === `G ${key}`);
        if (item) router.push(item.href);
      } else if (key === "G") {
        leader = true;
        clearTimeout(timer);
        timer = setTimeout(() => (leader = false), 800);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      clearTimeout(timer);
    };
  }, [open, router]);

  const run = (action: () => void) => {
    setOpen(false);
    action();
  };

  return (
    <CommandMenuContext.Provider value={setOpen}>
      {children}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="p-0">
          <DialogTitle className="sr-only">Command menu</DialogTitle>
          <DialogDescription className="sr-only">Go to a page or run an action.</DialogDescription>
          <Command loop>
            <CommandInput placeholder="Go to, or run a command…" />
            <CommandList>
              <CommandEmpty>Nothing matches.</CommandEmpty>
              <CommandGroup heading="Go to">
                {[...NAV, ...(plugins.data ?? []).map(pluginItem)].map((item) => (
                  <CommandItem
                    key={item.href}
                    value={`${fullTitle(item)} ${item.description}`}
                    onSelect={() => run(() => router.push(item.href))}
                  >
                    <item.icon />
                    <span>{fullTitle(item)}</span>
                    <span className="ml-auto flex gap-1">
                      {item.shortcut
                        .split(" ")
                        .filter(Boolean)
                        .map((k) => (
                          <Kbd key={k}>{k}</Kbd>
                        ))}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
              {experiments.data && experiments.data.length > 0 && (
                <CommandGroup heading="Experiments">
                  {experiments.data.map((e) => (
                    <CommandItem
                      key={e.name}
                      value={`${e.name} ${e.domain_title} ${e.question ?? ""}`}
                      onSelect={() => run(() => router.push(experimentHref(e.name, e.axis)))}
                    >
                      <FlaskConical />
                      <span className="font-mono">{e.name}</span>
                      <span className="text-muted-foreground ml-auto text-xs">{e.status}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
              <CommandGroup heading="Actions">
                <CommandItem
                  value="Toggle theme dark light"
                  onSelect={() => run(() => setTheme(resolvedTheme === "dark" ? "light" : "dark"))}
                >
                  <Moon />
                  <span>Toggle theme</span>
                </CommandItem>
                {canPick && (
                  <CommandItem
                    value="Pick parts for your agent tap select card row change layout"
                    onSelect={() => run(() => setTapping(true))}
                  >
                    <Crosshair />
                    <span>Pick parts for your agent (or Shift+click)</span>
                  </CommandItem>
                )}
                <CommandItem
                  value="Docs documentation architecture roadmap"
                  onSelect={() => run(() => window.open(DOCS, "_blank", "noopener,noreferrer"))}
                >
                  <BookOpen />
                  <span>Docs</span>
                </CommandItem>
              </CommandGroup>
            </CommandList>
          </Command>
        </DialogContent>
      </Dialog>
    </CommandMenuContext.Provider>
  );
}
