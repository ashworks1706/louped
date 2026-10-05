"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import { askToNotify } from "@/components/notifier";
import { Button } from "@/components/ui/button";
import { launch } from "@/lib/api";
import { jobHref } from "@/lib/href";

/** Starts `louped examples` and opens its job: example runs for every page, on a tiny model. */
export function ExamplesButton({ variant = "default" }: { variant?: "default" | "outline" }) {
  const router = useRouter();
  const client = useQueryClient();
  const go = useMutation({
    mutationFn: () => launch({ id: "examples", options: {} }),
    meta: { action: "Load examples" },
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      router.push(jobHref(job.id));
    },
  });
  return (
    <Button
      size="sm"
      variant={variant}
      onClick={() => {
        askToNotify();
        go.mutate();
      }}
      disabled={go.isPending}
    >
      <Sparkles /> Load examples
    </Button>
  );
}
