"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Lightbulb, Plus } from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";
import { useState } from "react";
import { toast } from "sonner";

import { DeleteButton } from "@/components/delete-button";
import { EmptyState } from "@/components/empty-state";
import { Segmented } from "@/components/experiments-list";
import { Help } from "@/components/help";
import { Part, part, partId } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  createFeedback,
  deleteFeedback,
  openedFeedback,
  q,
  saveFeedback,
  type Feedback,
  type FeedbackDraft,
  type FeedbackForm,
} from "@/lib/api";
import { ago } from "@/lib/format";
import { cn } from "@/lib/utils";

const NEW = "new";

/** Requests for louped itself: an agent drafts one (draft_feedback), the person reads and edits
 * it here, then files it through GitHub's own new-issue page, prefilled. louped holds no GitHub
 * token, so nothing is sent until the person submits it there. */
export function FeedbackView() {
  const [id, setId] = useQueryState("id", parseAsString);
  const health = useQuery(q.health());
  const can = !!health.data?.launching;
  // a shared server or a published dashboard keeps no requests: the drafts are this machine's
  const list = useQuery({ ...q.feedback(), enabled: can });
  const forms = useQuery({ ...q.feedbackForms(), enabled: can });
  if (health.data && !can)
    return (
      <EmptyState
        icon={Lightbulb}
        title="Feedback is off here"
        body="Requests for louped are kept on the machine that runs the work, where your agent drafts them."
        command="louped serve"
      />
    );
  return (
    <QueryState query={list}>
      {(all) => {
        if (all.length === 0 && id !== NEW)
          return (
            <EmptyState
              icon={Lightbulb}
              title="No requests yet"
              body="When louped lacks something the work needs, your agent drafts a request here. Read it, edit it, then file it on GitHub."
            >
              <Button size="sm" onClick={() => void setId(NEW)} {...part("feedback/new")}>
                <Plus /> New request
              </Button>
            </EmptyState>
          );
        const open = id === NEW ? null : id ? all.find((f) => f.id === id) : all[0];
        return (
          <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
            <section className="flex flex-col gap-2">
              <div className="flex h-8 items-center justify-between">
                <h2
                  className="flex items-center gap-1.5 text-sm font-medium"
                  {...part("feedback/heading")}
                >
                  Requests
                  <Help>
                    Drafts stay on this machine (.louped/feedback). Open on GitHub fills in
                    GitHub&apos;s new-issue form; you submit it there, signed in as yourself.
                  </Help>
                </h2>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => void setId(NEW)}
                  {...part("feedback/new")}
                >
                  <Plus /> New
                </Button>
              </div>
              <ul className="flex flex-col gap-1">
                {all.map((f) => (
                  <li key={f.id}>
                    <button
                      type="button"
                      onClick={() => void setId(f.id)}
                      aria-current={open?.id === f.id ? "true" : undefined}
                      className={cn(
                        "hover:bg-accent/60 flex w-full flex-col gap-1 rounded-md border px-3 py-2 text-left",
                        open?.id === f.id && "bg-accent/60",
                      )}
                      {...part(partId("feedback/item", f.id))}
                    >
                      <span className="line-clamp-2 text-sm">{f.title}</span>
                      <span className="text-muted-foreground flex items-center gap-2 text-xs">
                        <Badge variant="outline" className="capitalize">
                          {f.kind}
                        </Badge>
                        {f.opened
                          ? `opened on GitHub ${ago(f.opened)}`
                          : `draft, ${ago(f.created)}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
            {open === undefined ? (
              <p className="text-muted-foreground text-sm" {...part("feedback/missing")}>
                No request {id}. It may have been deleted or filed.
              </p>
            ) : (
              !!forms.data?.length && (
                <Editor
                  key={open?.id ?? NEW}
                  item={open}
                  forms={forms.data}
                  onSaved={(f) => void setId(f.id)}
                />
              )
            )}
          </div>
        );
      }}
    </QueryState>
  );
}

function Editor({
  item,
  forms,
  onSaved,
}: {
  /** null: a new request. */
  item: Feedback | null;
  forms: FeedbackForm[];
  onSaved: (f: Feedback) => void;
}) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<FeedbackDraft>(
    item
      ? { kind: item.kind, title: item.title, fields: item.fields ?? {} }
      : { kind: "feature", title: "", fields: {} },
  );
  const form = forms.find((f) => f.kind === draft.kind) ?? forms[0];
  const fields = draft.fields ?? {};
  const dirty =
    !item ||
    draft.kind !== item.kind ||
    draft.title !== item.title ||
    form.fields.some((f) => (fields[f.id] ?? "") !== (item.fields?.[f.id] ?? ""));
  const save = useMutation({
    mutationFn: () => {
      const kept = Object.fromEntries(
        form.fields.filter((f) => fields[f.id]?.trim()).map((f) => [f.id, fields[f.id]]),
      );
      const body = { ...draft, title: draft.title.trim(), fields: kept };
      return item ? saveFeedback(item.id, body) : createFeedback(body);
    },
    meta: { action: "Save request" },
    onSuccess: (done) => {
      client.setQueryData<Feedback[]>(["feedback"], (all = []) => [
        done,
        ...all.filter((f) => f.id !== done.id),
      ]);
      void client.invalidateQueries({ queryKey: ["feedback"] });
      toast("Saved");
      onSaved(done);
    },
  });
  const opened = useMutation({
    mutationFn: () => openedFeedback(item!.id),
    meta: { action: "Mark opened" },
    onSuccess: () => void client.invalidateQueries({ queryKey: ["feedback"] }),
  });
  return (
    <Part id="feedback/editor" className="flex flex-col gap-4">
      <h2 className="text-sm font-medium" {...part("feedback/editor/heading")}>
        {item ? "Request" : "New request"}
      </h2>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty && draft.title.trim()) save.mutate();
        }}
      >
        <Segmented
          label="Kind"
          value={draft.kind}
          options={forms.map((f) => ({
            value: f.kind,
            title: f.kind === "feature" ? "Feature" : "Bug",
            address: partId("feedback/kind", f.kind),
          }))}
          onChange={(kind) => setDraft({ ...draft, kind })}
        />
        <label className="flex flex-col gap-1 text-xs" {...part("feedback/title")}>
          Title
          <Input
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            placeholder={draft.kind === "feature" ? "Compare two checkpoints' circuits" : ""}
            maxLength={200}
            required
          />
        </label>
        {form.fields.map((f) => (
          <label
            key={f.id}
            className="flex flex-col gap-1 text-xs"
            {...part(partId("feedback/field", f.id))}
          >
            {f.label}
            <Textarea
              value={fields[f.id] ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, fields: { ...fields, [f.id]: e.target.value } })
              }
              className="min-h-24"
            />
          </label>
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="submit"
            size="sm"
            variant={dirty ? "default" : "outline"}
            disabled={!dirty || !draft.title.trim() || save.isPending}
            {...part("feedback/save")}
          >
            Save
          </Button>
          {item &&
            (dirty ? (
              <Button size="sm" variant="outline" disabled {...part("feedback/open")}>
                <ExternalLink /> Save to open on GitHub
              </Button>
            ) : (
              <Button size="sm" variant="outline" asChild {...part("feedback/open")}>
                <a
                  href={item.issue_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => !item.opened && opened.mutate()}
                >
                  <ExternalLink /> Open on GitHub
                </a>
              </Button>
            ))}
          {item && (
            <div className="ml-auto" {...part("feedback/delete")}>
              <DeleteButton
                what="request"
                name={item.title}
                undo="It moves to .louped/trash/feedback; move it back to restore it."
                remove={() => deleteFeedback(item.id)}
                then="/feedback/"
              />
            </div>
          )}
        </div>
        {item?.opened && (
          <p className="text-muted-foreground text-xs">
            Opened on GitHub {ago(item.opened)}. Once you submitted it there, delete it here.
          </p>
        )}
      </form>
    </Part>
  );
}
