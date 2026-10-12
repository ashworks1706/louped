"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { FormDialog, Label, NAME_PATTERN, text } from "@/components/form-dialog";
import { part } from "@/components/parts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { createExperiment, q } from "@/lib/api";
import { experimentHref } from "@/lib/href";

/** Writes experiments/<name>/, in the project when one is given, and opens its page to write its
 * question. */
export function NewExperiment({ project }: { project: string | null }) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const router = useRouter();
  const domains = useQuery({ ...q.domains(), enabled: open });
  const make = useMutation({
    mutationFn: createExperiment,
    meta: { action: "Create experiment" },
    onSuccess: (e) => {
      if (project) void client.invalidateQueries({ queryKey: ["project", project] });
      void client.invalidateQueries({ queryKey: ["projects"] });
      void client.invalidateQueries({ queryKey: ["experiments"] });
      void client.invalidateQueries({ queryKey: ["launchables"] });
      setOpen(false);
      toast(`Created ${e.name}`, {
        description: `experiments/${e.name}/${project ? `, in ${project}` : ""}`,
      });
      router.push(experimentHref(e.name, "design"));
    },
  });
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setOpen(true)}
        {...part("experiments/new")}
      >
        <FlaskConical /> New experiment
      </Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        id="new-experiment"
        title={project ? `New experiment in ${project}` : "New experiment"}
        description={`Writes experiments/<name>/ with its README to fill in and a run.py, active${project ? ", with project: in its front matter" : ""}.`}
        pending={make.isPending}
        submit="Create"
        onSubmit={(form) =>
          make.mutate({ name: text(form, "name"), domain: text(form, "domain"), project })
        }
      >
        <Label text="Name, for the question">
          <Input
            name="name"
            required
            pattern={NAME_PATTERN}
            title="Lowercase letters, digits and -"
            placeholder="does-pushback-flip-answers"
            className="font-mono placeholder:font-sans"
            autoComplete="off"
          />
        </Label>
        <Label text="Domain">
          <NativeSelect name="domain" required className="w-full" key={domains.data?.length}>
            {(domains.data ?? []).map((d) => (
              <option key={d.key} value={d.key}>
                {d.title}
              </option>
            ))}
          </NativeSelect>
        </Label>
      </FormDialog>
    </>
  );
}
