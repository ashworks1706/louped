"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Textarea } from "@/components/ui/textarea";
import { q } from "@/lib/api";

/** Markdown with an Edit button when this server allows edits: the text beside its rendering as
 * you type, saved in place. source is what is edited, when it differs from what is shown (a
 * README's front matter); save writes it. */
export function EditableMarkdown({
  name,
  children,
  shown,
  source,
  save,
}: {
  /** The file, as the person knows it: README.md, report.md. */
  name: string;
  /** What shows when not editing; the rendered text by default. */
  children?: ReactNode;
  shown: string;
  source?: () => Promise<string>;
  save: (text: string) => Promise<unknown>;
}) {
  const health = useQuery(q.health());
  const [draft, setDraft] = useState<string | null>(null);
  const open = useMutation({
    mutationFn: async () => (source ? source() : shown),
    meta: { action: `Open ${name}` },
    onSuccess: setDraft,
  });
  const write = useMutation({
    mutationFn: save,
    meta: { action: `Save ${name}` },
    onSuccess: () => {
      setDraft(null);
      toast(`${name} saved`);
    },
  });
  if (draft === null)
    return (
      <div className="group relative">
        {health.data?.launching && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute top-0 right-0"
            onClick={() => open.mutate()}
            disabled={open.isPending}
            aria-label={`Edit ${name}`}
          >
            <Pencil /> Edit
          </Button>
        )}
        {children ?? <Markdown>{shown}</Markdown>}
      </div>
    );
  const keys = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "s") {
      e.preventDefault();
      write.mutate(draft);
    } else if (e.key === "Escape") setDraft(null);
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-4 lg:grid-cols-2">
        <Textarea
          aria-label={name}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={keys}
          spellCheck
          autoFocus
          className="min-h-96 font-mono text-xs leading-relaxed"
        />
        <div className="min-w-0 rounded-md border px-4 py-3" aria-label="Preview">
          <Markdown>{draft}</Markdown>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={() => write.mutate(draft)} disabled={write.isPending}>
          Save
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
          Cancel
        </Button>
        <span className="text-muted-foreground text-xs">
          <Kbd>⌘S</Kbd> saves, <Kbd>Esc</Kbd> cancels
        </span>
      </div>
    </div>
  );
}
