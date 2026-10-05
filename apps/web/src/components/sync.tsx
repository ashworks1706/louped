"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cloud, CloudDownload, CloudUpload, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { part, useRules } from "@/components/parts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, connectRemote, importResult, pullRuns, pushRuns, q } from "@/lib/api";
import { jobHref } from "@/lib/href";
import { cn } from "@/lib/utils";

/** Push and Pull with the project's remote, when it has one. */
export function Sync() {
  const rule = useRules();
  const client = useQueryClient();
  const health = useQuery(q.health());
  const remote = health.data?.remote;
  const [connecting, setConnecting] = useState(false);
  // a missing Hugging Face token opens Connect instead of an error
  const needsToken = (error: Error) => error instanceof ApiError && error.status === 401;
  const push = useMutation({
    mutationFn: pushRuns,
    meta: { action: "Push", quiet: needsToken },
    onError: (e) => needsToken(e) && setConnecting(true),
    onSuccess: (done) =>
      toast(done.bundle ? `${done.runs.length} runs pushed` : "Nothing new to push", {
        description: <span className="font-mono">{done.remote}</span>,
      }),
  });
  const pull = useMutation({
    mutationFn: pullRuns,
    meta: { action: "Pull", quiet: needsToken },
    onError: (e) => needsToken(e) && setConnecting(true),
    onSuccess: (found) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["runs"] });
      const runs = found.reduce((n, d) => n + d.runs.length, 0);
      toast(found.length ? `${runs} runs pulled` : "Nothing new to pull", {
        description: found.length
          ? `From ${[...new Set(found.map((d) => d.host))].join(", ")}`
          : remote,
      });
    },
  });
  return (
    <>
      {remote ? (
        <>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => pull.mutate()}
            {...part("runs/action/pull")}
            className={cn(rule("runs/action/pull").hidden && "hidden")}
            disabled={pull.isPending}
            title={`Add the runs pushed to ${remote}`}
          >
            <CloudDownload /> Pull
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => push.mutate()}
            {...part("runs/action/push")}
            className={cn(rule("runs/action/push").hidden && "hidden")}
            disabled={push.isPending}
            title={`Push this louped's new runs to ${remote}`}
          >
            <CloudUpload /> Push
          </Button>
        </>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setConnecting(true)}
          {...part("runs/action/connect")}
          className={cn(rule("runs/action/connect").hidden && "hidden")}
          title="Share runs through a remote"
        >
          <Cloud /> Connect
        </Button>
      )}
      <Connect open={connecting} onOpenChange={setConnecting} remote={remote ?? ""} />
    </>
  );
}

/** Sets the remote runs are pushed to and pulled from, and a Hugging Face token for an hf:// one. */
function Connect({
  open,
  onOpenChange,
  remote,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  remote: string;
}) {
  const client = useQueryClient();
  const connect = useMutation({
    mutationFn: connectRemote,
    meta: { action: "Connect" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["health"] });
      onOpenChange(false);
      toast("Remote set", { description: <span className="font-mono">{done.remote}</span> });
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">Connect a remote</DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Where runs are pushed and pulled, saved in louped.toml. The token stays on this machine,
            where Hugging Face&apos;s own tools keep it.
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            connect.mutate({
              remote: String(form.get("remote") ?? ""),
              token: String(form.get("token") ?? ""),
            });
          }}
        >
          <label className="flex flex-col gap-1 text-xs">
            Remote
            <Input
              name="remote"
              defaultValue={remote}
              placeholder="Empty: a private HF bucket of your own"
              className="font-mono placeholder:font-sans"
              autoComplete="off"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span>
              Hugging Face token{" "}
              <a
                className="text-muted-foreground underline underline-offset-2"
                href="https://huggingface.co/settings/tokens"
                target="_blank"
                rel="noreferrer"
              >
                (write access)
              </a>
            </span>
            <Input
              name="token"
              type="password"
              placeholder="Empty if this machine is signed in"
              className="font-mono placeholder:font-sans"
              autoComplete="off"
            />
          </label>
          <Button type="submit" size="sm" className="self-end" disabled={connect.isPending}>
            Connect
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Takes the louped-result-….tar.gz an exported job wrote elsewhere; its runs join Runs. */
export function ImportResult() {
  const rule = useRules();
  const client = useQueryClient();
  const router = useRouter();
  const picker = useRef<HTMLInputElement>(null);
  const bring = useMutation({
    mutationFn: importResult,
    meta: { action: "Import" },
    onSuccess: (done) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      void client.invalidateQueries({ queryKey: ["runs"] });
      toast(`${done.runs.length} runs imported from ${done.host}`, {
        description: done.skipped.length ? `${done.skipped.length} were already here.` : undefined,
      });
      if (done.job) router.push(jobHref(done.job));
    },
  });
  return (
    <>
      <input
        ref={picker}
        type="file"
        accept=".gz,.tgz,application/gzip"
        className="hidden"
        aria-label="Result archive"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) bring.mutate(file);
          e.target.value = "";
        }}
      />
      <Button
        variant="ghost"
        size="sm"
        onClick={() => picker.current?.click()}
        {...part("runs/action/import")}
        className={cn(rule("runs/action/import").hidden && "hidden")}
        disabled={bring.isPending}
        title="The louped-result-….tar.gz a job exported to Sol, a cluster or a VM wrote"
      >
        <Upload /> Import result
      </Button>
    </>
  );
}
