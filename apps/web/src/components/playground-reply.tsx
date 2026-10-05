"use client";

import { parseAsString, useQueryStates } from "nuqs";
import { useCallback, useEffect, useRef, useState } from "react";

import { Field, type Setup } from "@/components/playground-fields";
import { part, partId } from "@/components/parts";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { TabsContent } from "@/components/ui/tabs";
import { generate, type View } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The Reply tool: the base and the intervened reply streamed side by side, each pushed back on
 * once it ends when a follow-up is set. */
export function useReplyTab(setup: Setup) {
  const { interventions, live, intervened, gen, label } = setup;
  const [s, set] = useQueryStates({ follow: parseAsString.withDefault("") });
  const base = useReply();
  const edited = useReply();
  const baseAgain = useReply();
  const editedAgain = useReply();
  const run = (prompt: string) => {
    // With a follow-up, each side's reply is pushed back on once it ends, in its own history.
    const follow = s.follow.trim();
    const then = (again: typeof baseAgain, req: Omit<Parameters<typeof generate>[0], "prompt">) =>
      follow
        ? (text: string) =>
            again.start({
              ...req,
              prompt: follow,
              history: [
                { role: "user", content: prompt },
                { role: "assistant", content: text.trim() },
              ],
            })
        : undefined;
    const plain = { interventions: [], adapters: [], history: [], ...gen };
    const changed = { interventions, adapters: live, history: [], ...gen };
    baseAgain.reset();
    editedAgain.reset();
    base.start({ prompt, ...plain }, then(baseAgain, plain));
    if (intervened) edited.start({ prompt, ...changed }, then(editedAgain, changed));
    else edited.reset();
  };
  const keep = () => {
    const sides = [
      ["base", base, baseAgain],
      ["intervention", edited, editedAgain],
    ] as const;
    const ran = sides.filter(([, r]) => r.ran && !r.pending && !r.error);
    if (!ran.length || sides.some(([, r, a]) => r.pending || a.pending)) return null;
    const follow = ran.some(([, , a]) => a.ran);
    const reply: View = {
      kind: "table",
      title: "Replies",
      columns: follow ? ["side", "reply", "after the follow-up"] : ["side", "reply"],
      rows: ran.map(([side, r, a]) =>
        follow ? [side, r.text.trim(), a.text.trim()] : [side, r.text.trim()],
      ),
    };
    const settings = { interventions, adapters: live, follow: s.follow.trim(), ...gen };
    return { prompt: setup.prompt, settings, label, views: [reply] };
  };
  const streaming = base.pending || edited.pending || baseAgain.pending || editedAgain.pending;
  const stop = () => {
    base.stop();
    edited.stop();
    baseAgain.stop();
    editedAgain.stop();
  };
  return {
    ready: true,
    busy: false,
    run,
    keep,
    streaming,
    stop,
    follow: s.follow,
    setFollow: (follow: string) => void set({ follow }),
    base,
    edited,
    baseAgain,
    editedAgain,
  };
}

/** The Reply tab: the follow-up to push back with, and the two replies. */
export function ReplyTab({ tool, label }: { tool: ReturnType<typeof useReplyTab>; label: string }) {
  const again = tool.follow.trim();
  return (
    <TabsContent value="reply" className="flex flex-col gap-4 pt-4">
      <Field label="Follow-up">
        <Input
          aria-label="Follow-up"
          value={tool.follow}
          placeholder="Then push back, e.g. I don't think that's right. Are you sure?"
          onChange={(e) => tool.setFollow(e.target.value)}
          className="h-8 text-sm"
        />
      </Field>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Reply title="Base" state={tool.base} again={again ? tool.baseAgain : undefined} />
        <Reply
          title="With intervention"
          badge={
            <Badge variant="intervention" className="block max-w-full min-w-0 shrink truncate">
              {label}
            </Badge>
          }
          state={tool.edited}
          again={again ? tool.editedAgain : undefined}
          intervention
        />
      </div>
    </TabsContent>
  );
}

function Reply({
  title,
  badge,
  state,
  again,
  intervention,
}: {
  title: string;
  badge?: React.ReactNode;
  state: ReplyState;
  again?: ReplyState;
  intervention?: boolean;
}) {
  const text = state.text.trimStart();
  const second = again?.text.trimStart();
  return (
    <section
      data-testid={`reply-${intervention ? "intervention" : "base"}`}
      {...part(partId("playground/reply", intervention ? "intervention" : "base"))}
      className={cn(
        "flex min-h-40 flex-col rounded-xl border",
        intervention && "border-intervention/40",
      )}
    >
      <header className="flex h-11 items-center justify-between gap-3 border-b px-4">
        <span className="shrink-0 text-sm font-medium">{title}</span>
        <span className="flex min-w-0 justify-end overflow-hidden">{badge}</span>
      </header>
      <div className="flex-1 p-4 text-sm leading-relaxed whitespace-pre-wrap">
        {state.error ? (
          <span className="text-negative">{state.error.message}</span>
        ) : text ? (
          text
        ) : state.pending ? (
          <span className="text-muted-foreground animate-pulse">Generating…</span>
        ) : state.ran ? (
          <span className="text-muted-foreground">(empty reply)</span>
        ) : (
          <span className="text-muted-foreground">Run a prompt to see the reply.</span>
        )}
      </div>
      {again?.ran && (
        <div
          data-testid="follow-up"
          className="border-t p-4 text-sm leading-relaxed whitespace-pre-wrap"
        >
          <span className="text-muted-foreground mb-2 block text-xs">After the follow-up</span>
          {again.error ? (
            <span className="text-negative">{again.error.message}</span>
          ) : second ? (
            second
          ) : again.pending ? (
            <span className="text-muted-foreground animate-pulse">Generating…</span>
          ) : (
            <span className="text-muted-foreground">(empty reply)</span>
          )}
        </div>
      )}
    </section>
  );
}

type ReplyState = { text: string; pending: boolean; error: Error | null; ran: boolean };
const IDLE: ReplyState = { text: "", pending: false, error: null, ran: false };

/** One side's reply, filled as it streams in; a new start or stop aborts the one in flight. */
function useReply() {
  const [reply, setReply] = useState(IDLE);
  const live = useRef<AbortController | null>(null);
  const stop = useCallback(() => live.current?.abort(), []);
  useEffect(() => stop, [stop]);
  /** onDone gets the whole reply when it ends unstopped and without error. */
  const start = (req: Parameters<typeof generate>[0], onDone?: (text: string) => void) => {
    stop();
    const c = new AbortController();
    live.current = c;
    setReply({ ...IDLE, pending: true, ran: true });
    let text = "";
    generate(
      req,
      (t) => {
        text += t;
        setReply((r) => ({ ...r, text: r.text + t }));
      },
      c.signal,
    )
      .then(() => {
        if (!c.signal.aborted) onDone?.(text);
      })
      .catch((error: Error) => {
        if (!c.signal.aborted) setReply((r) => ({ ...r, error }));
      })
      .finally(() => {
        if (live.current === c) setReply((r) => ({ ...r, pending: false }));
      });
  };
  const reset = () => {
    stop();
    setReply(IDLE);
  };
  return { ...reply, start, stop, reset };
}
