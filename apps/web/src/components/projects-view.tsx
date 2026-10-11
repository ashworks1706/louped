"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, FlaskConical, FolderKanban, Pencil, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { parseAsString, useQueryState } from "nuqs";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { DomainGroups, StatusLabel } from "@/components/experiments-list";
import { Help } from "@/components/help";
import { EditableText } from "@/components/markdown-editor";
import { arrange, Part, part, partId, PartData, useRules } from "@/components/parts";
import { QueryState } from "@/components/query-state";
import { RunsTable } from "@/components/runs-table";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import {
  createExperiment,
  createProject,
  projectReadme,
  q,
  saveProjectMeta,
  saveProjectReadme,
  type Project,
  type ProjectDetail,
  type ProjectMeta,
} from "@/lib/api";
import { ago } from "@/lib/format";
import { experimentHref, host, projectHref } from "@/lib/href";
import { cn } from "@/lib/utils";

const STATUSES = ["active", "parked", "done"] as const;
/** A project's name: its folder under projects/, as louped.core.paths.NAME allows. */
const NAME_PATTERN = "[a-z0-9][a-z0-9\\-]{0,63}";

/** Every project as a card: what it is for, where it stands, and its experiments and runs. */
export function ProjectsList() {
  const projects = useQuery(q.projects());
  const health = useQuery(q.health());
  return (
    <QueryState query={projects}>
      {(all) =>
        all.length === 0 ? (
          health.data?.launching ? (
            <EmptyState
              icon={FolderKanban}
              title="No projects yet"
              body="A project groups experiments toward one goal: projects/<name>/README.md. An experiment joins it with project: <name> in its own README."
            >
              <NewProject />
            </EmptyState>
          ) : (
            <EmptyState
              icon={FolderKanban}
              title="No projects yet"
              body="A project groups experiments toward one goal: projects/<name>/README.md. An experiment joins it with project: <name> in its own README."
              command="louped project new my-project"
            />
          )
        ) : (
          <section className="flex flex-col gap-3">
            <PartData
              prefix="projects/card"
              resolve={(id) => all.find((p) => partId("projects/card", p.name) === id)}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-medium" {...part("projects/count")}>
                <span className="font-mono tabular-nums">{all.length}</span>{" "}
                {all.length === 1 ? "project" : "projects"}
              </h2>
              {health.data?.launching && <NewProject />}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {all.map((p) => (
                <ProjectCard key={p.name} project={p} />
              ))}
            </div>
          </section>
        )
      }
    </QueryState>
  );
}

function ProjectCard({ project: p }: { project: Project }) {
  return (
    <Link
      href={projectHref(p.name)}
      {...part(partId("projects/card", p.name))}
      className="hover:bg-accent/40 focus-visible:ring-ring/50 flex min-w-0 flex-col gap-2 rounded-xl border p-4 transition-colors outline-none focus-visible:ring-[3px]"
    >
      <div className="flex items-center gap-3">
        <h3 className="min-w-0 flex-1 truncate text-sm font-medium" title={p.title}>
          {p.title}
        </h3>
        {p.missing ? <MissingLabel /> : <StatusLabel status={p.status} />}
      </div>
      <p className="text-muted-foreground -mt-1 truncate font-mono text-xs">{p.name}</p>
      <p className="text-muted-foreground line-clamp-2 text-sm leading-snug">
        {p.missing
          ? `Experiments name it, but projects/${p.name}/README.md does not exist.`
          : p.summary || "No summary written yet."}
      </p>
      {p.tags.length > 0 && <Tags tags={p.tags} />}
      <div className="text-muted-foreground mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2.5 text-xs whitespace-nowrap">
        <span>
          <span className="text-foreground font-mono tabular-nums">{p.experiments.length}</span>{" "}
          {p.experiments.length === 1 ? "experiment" : "experiments"}
        </span>
        <span>
          <span className="text-foreground font-mono tabular-nums">{p.runs}</span>{" "}
          {p.runs === 1 ? "run" : "runs"}
        </span>
        <span className="truncate">{p.last_run ? `last ${ago(p.last_run)}` : "no runs yet"}</span>
      </div>
    </Link>
  );
}

/** A project with no README: a neutral mark, like a status, since it is not a delta. */
function MissingLabel() {
  return (
    <span className="text-muted-foreground inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
      <span className="border-muted-foreground size-1.5 rounded-full border border-dashed" />
      no README
    </span>
  );
}

function Tags({ tags }: { tags: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1">
      {tags.map((t) => (
        <li
          key={t}
          className="bg-muted text-muted-foreground rounded-md border px-1.5 py-0.5 font-mono text-[11px]"
        >
          {t}
        </li>
      ))}
    </ul>
  );
}

/** One project, by ?name=: its goal, its metadata, its experiments by domain and their runs. */
export function ProjectView() {
  const [name] = useQueryState("name", parseAsString);
  if (!name) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={FolderKanban}
          title="No project selected"
          body="Open one from the projects."
          action={{ href: "/projects/", label: "Projects" }}
        />
      </section>
    );
  }
  return <ProjectLoaded name={name} />;
}

function ProjectLoaded({ name }: { name: string }) {
  const project = useQuery(q.project(name));
  if (!project.data) {
    return (
      <section className="mx-auto max-w-6xl px-6 py-8">
        <QueryState query={project}>{() => null}</QueryState>
      </section>
    );
  }
  const p = project.data;
  return (
    <>
      <ProjectHeader project={p} />
      <div className="mx-auto grid max-w-6xl gap-8 px-6 py-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="flex min-w-0 flex-col gap-8">
          {p.missing ? <Missing project={p} /> : <Readme project={p} />}
          <Experiments project={p} />
          <Runs project={p} />
        </div>
        <Metadata project={p} />
      </div>
    </>
  );
}

function ProjectHeader({ project: p }: { project: ProjectDetail }) {
  const health = useQuery(q.health());
  const rule = useRules();
  const acts = health.data?.launching && !p.missing;
  return (
    <header className="border-b">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6">
        <Link
          href="/projects/"
          className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs"
          {...part("projects/back")}
        >
          <ArrowLeft className="size-3" /> Projects
        </Link>
        <div className="flex flex-col items-start gap-x-6 gap-y-3 sm:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-xl font-semibold tracking-tight" {...part("projects/title")}>
                {p.title}
              </h1>
              <span {...part("projects/status")} className="inline-flex">
                {p.missing ? <MissingLabel /> : <StatusLabel status={p.status} />}
              </span>
            </div>
            <p className="max-w-3xl text-[15px] leading-snug" {...part("projects/summary")}>
              <span className="text-muted-foreground font-mono text-xs">{p.name}</span>
              {p.summary && <span className="mt-1 block font-medium">{p.summary}</span>}
            </p>
          </div>
          {acts && (
            <div className="flex flex-wrap items-start gap-2">
              <span
                {...part("projects/new-experiment")}
                className={cn(rule("projects/new-experiment").hidden && "hidden")}
              >
                <NewExperiment project={p.name} />
              </span>
              <span
                {...part("projects/edit")}
                className={cn(rule("projects/edit").hidden && "hidden")}
              >
                <EditMeta project={p} />
              </span>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

/** A name experiments give with no README: said, never left out, and made in one click. */
function Missing({ project: p }: { project: ProjectDetail }) {
  const health = useQuery(q.health());
  const client = useQueryClient();
  const make = useMutation({
    mutationFn: () => createProject({ name: p.name, title: p.name }),
    meta: { action: "Create project" },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["project", p.name] });
      void client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
  return (
    <div
      {...part("projects/missing")}
      className="flex flex-col items-start gap-3 rounded-xl border border-dashed px-4 py-4 text-sm"
    >
      <p>
        <span className="font-mono">projects/{p.name}/README.md</span> does not exist.{" "}
        {p.experiments.length}{" "}
        {p.experiments.length === 1 ? "experiment names" : "experiments name"} it with{" "}
        <span className="font-mono">project: {p.name}</span>.
      </p>
      {health.data?.launching ? (
        <Button
          size="sm"
          onClick={() => make.mutate()}
          disabled={make.isPending}
          {...part("projects/create")}
        >
          <Plus /> Create its README
        </Button>
      ) : (
        <code className="text-muted-foreground font-mono text-xs">louped project new {p.name}</code>
      )}
    </div>
  );
}

function Section({
  id,
  title,
  about,
  count,
  children,
}: {
  id: string;
  title: string;
  about: string;
  count?: number;
  children: React.ReactNode;
}) {
  const rule = useRules()(partId("projects/section", id));
  return (
    <Part id={partId("projects/section", id)} as="section" className="flex min-w-0 flex-col gap-3">
      <h2 className="flex items-center gap-1.5 text-sm font-medium">
        {rule.label ?? title}
        {count !== undefined && (
          <span className="text-muted-foreground font-mono text-xs tabular-nums">{count}</span>
        )}
        <Help>{rule.about ?? about}</Help>
      </h2>
      {children}
    </Part>
  );
}

function Readme({ project: p }: { project: ProjectDetail }) {
  const client = useQueryClient();
  return (
    <Section
      id="readme"
      title="README"
      about={`projects/${p.name}/README.md under its front matter: the goal, the background and notes. Edit saves the file in place.`}
    >
      <article className="min-w-0">
        <EditableText
          name="README.md"
          shown={p.readme}
          source={() => projectReadme(p.name)}
          save={async (text) => {
            await saveProjectReadme(p.name, text);
            await client.invalidateQueries({ queryKey: ["project", p.name] });
            await client.invalidateQueries({ queryKey: ["projects"] });
          }}
        />
      </article>
    </Section>
  );
}

function Experiments({ project: p }: { project: ProjectDetail }) {
  const health = useQuery(q.health());
  return (
    <Section
      id="experiments"
      title="Experiments"
      count={p.experiments.length}
      about="The experiments whose README names this project (project: in their front matter), by domain, with each one's status, question and latest result. Their folders stay under experiments/."
    >
      {p.experiments.length === 0 ? (
        health.data?.launching && !p.missing ? (
          <EmptyState
            icon={FlaskConical}
            title="No experiments in it yet"
            body="Start one here, or add project: <name> to an experiment's README."
          >
            <NewExperiment project={p.name} />
          </EmptyState>
        ) : (
          <EmptyState
            icon={FlaskConical}
            title="No experiments in it yet"
            body="An experiment joins it with project: <name> in its README."
            command={`louped new my-question --domain honesty --project ${p.name}`}
          />
        )
      ) : (
        <div className="flex flex-col gap-6">
          <DomainGroups experiments={p.experiments} showProject={false} />
        </div>
      )}
    </Section>
  );
}

function Runs({ project: p }: { project: ProjectDetail }) {
  return (
    <Section
      id="runs"
      title="Runs"
      count={p.runs.length}
      about="Every run of the project's experiments, newest first."
    >
      {p.runs.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No runs yet. They show here as its experiments run.
        </p>
      ) : (
        <RunsTable runs={p.runs} />
      )}
    </Section>
  );
}

const FIELDS = [
  { name: "links", label: "Links" },
  { name: "models", label: "Models" },
  { name: "datasets", label: "Datasets" },
  { name: "benchmarks", label: "Benchmarks" },
  { name: "tags", label: "Tags" },
] as const;

/** The front matter beside the text: where the project's parts are, and what it works on. */
function Metadata({ project: p }: { project: ProjectDetail }) {
  const rule = useRules();
  return (
    <aside className="min-w-0">
      <Section
        id="metadata"
        title="Metadata"
        about="The README's front matter: links by name, and the ids of the models, datasets and benchmarks it works on. Edit metadata changes it and keeps the text."
      >
        <dl className="flex flex-col divide-y rounded-xl border text-sm">
          {arrange([...FIELDS], (f) => partId("projects/meta", f.name), rule).map((f) => {
            const r = rule(partId("projects/meta", f.name));
            return (
              <div
                key={f.name}
                {...part(partId("projects/meta", f.name))}
                className="flex flex-col gap-1.5 px-3 py-2.5"
              >
                <dt className="text-muted-foreground flex items-center gap-1 text-xs">
                  {r.label ?? f.label}
                  {r.about && <Help>{r.about}</Help>}
                </dt>
                <dd className="min-w-0">
                  <Field project={p} field={f.name} />
                </dd>
              </div>
            );
          })}
        </dl>
      </Section>
    </aside>
  );
}

function Field({
  project: p,
  field,
}: {
  project: ProjectDetail;
  field: (typeof FIELDS)[number]["name"];
}) {
  const none = <span className="text-muted-foreground text-xs">none</span>;
  if (field === "links") {
    const links = Object.entries(p.links);
    if (links.length === 0) return none;
    return (
      <ul className="flex flex-col gap-1">
        {links.map(([label, url]) => (
          <li key={label} {...part(partId("projects/link", label))} className="min-w-0">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex max-w-full items-center gap-1.5 text-xs underline-offset-4 hover:underline"
              title={url}
            >
              <span className="font-medium">{label}</span>
              <span className="text-muted-foreground truncate">{host(url)}</span>
              <ExternalLink className="text-muted-foreground size-3 shrink-0" />
            </a>
          </li>
        ))}
      </ul>
    );
  }
  if (field === "tags") return p.tags.length ? <Tags tags={p.tags} /> : none;
  const ids = p[field];
  if (ids.length === 0) return none;
  return (
    <ul className="flex flex-col gap-0.5">
      {ids.map((id) => (
        <li key={id} className="truncate font-mono text-xs" title={id}>
          {id}
        </li>
      ))}
    </ul>
  );
}

/** A dialog's form, its fields as labels over inputs. */
function FormDialog({
  open,
  onOpenChange,
  id,
  title,
  description,
  children,
  onSubmit,
  pending,
  submit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  id: string;
  title: string;
  description: string;
  children: React.ReactNode;
  onSubmit: (form: FormData) => void;
  pending: boolean;
  submit: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 p-5" {...part(partId("projects/dialog", id))}>
        <div className="flex flex-col gap-1">
          <DialogTitle className="text-sm font-medium">{title}</DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            {description}
          </DialogDescription>
        </div>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(new FormData(e.currentTarget));
          }}
        >
          {children}
          <Button type="submit" size="sm" className="self-end" disabled={pending}>
            {submit}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      {text}
      {children}
    </label>
  );
}

const text = (form: FormData, key: string) => String(form.get(key) ?? "").trim();
/** A comma-separated field as its items. */
const list = (form: FormData, key: string) =>
  text(form, key)
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

function StatusSelect({ value }: { value: ProjectMeta["status"] }) {
  return (
    <NativeSelect name="status" defaultValue={value} className="w-full">
      {STATUSES.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </NativeSelect>
  );
}

/** Writes projects/<name>/README.md and opens its page. */
function NewProject() {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const router = useRouter();
  const rule = useRules();
  const make = useMutation({
    mutationFn: createProject,
    meta: { action: "Create project" },
    onSuccess: (p) => {
      void client.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      toast(`Created ${p.title}`, { description: `projects/${p.name}/README.md` });
      router.push(projectHref(p.name));
    },
  });
  return (
    <>
      <Button
        size="sm"
        onClick={() => setOpen(true)}
        {...part("projects/new")}
        className={cn(rule("projects/new").hidden && "hidden")}
      >
        <Plus /> New project
      </Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        id="new-project"
        title="New project"
        description="Writes projects/<name>/README.md with this front matter and sections to fill in."
        pending={make.isPending}
        submit="Create"
        onSubmit={(form) =>
          make.mutate({
            name: text(form, "name"),
            title: text(form, "title"),
            summary: text(form, "summary"),
            status: text(form, "status") as ProjectMeta["status"],
          })
        }
      >
        <Label text="Name">
          <Input
            name="name"
            required
            pattern={NAME_PATTERN}
            title="Lowercase letters, digits and -"
            placeholder="sycophancy-under-pushback"
            className="font-mono placeholder:font-sans"
            autoComplete="off"
          />
        </Label>
        <Label text="Title">
          <Input name="title" placeholder="Sycophancy under pushback" autoComplete="off" />
        </Label>
        <Label text="Summary, one line">
          <Input name="summary" autoComplete="off" />
        </Label>
        <Label text="Status">
          <StatusSelect value="active" />
        </Label>
      </FormDialog>
    </>
  );
}

/** Writes experiments/<name>/ in this project and opens its page, to write its question. */
function NewExperiment({ project }: { project: string }) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const router = useRouter();
  const domains = useQuery({ ...q.domains(), enabled: open });
  const make = useMutation({
    mutationFn: createExperiment,
    meta: { action: "Create experiment" },
    onSuccess: (e) => {
      void client.invalidateQueries({ queryKey: ["project", project] });
      void client.invalidateQueries({ queryKey: ["projects"] });
      void client.invalidateQueries({ queryKey: ["experiments"] });
      void client.invalidateQueries({ queryKey: ["launchables"] });
      setOpen(false);
      toast(`Created ${e.name}`, { description: `experiments/${e.name}/, in ${project}` });
      router.push(experimentHref(e.name, e.axis, "design"));
    },
  });
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <FlaskConical /> New experiment
      </Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        id="new-experiment"
        title={`New experiment in ${project}`}
        description="Writes experiments/<name>/ with its README to fill in and a run.py, active, with project: in its front matter."
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

/** Replaces the README's front matter; its text stays. */
function EditMeta({ project: p }: { project: ProjectDetail }) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (meta: ProjectMeta) => saveProjectMeta(p.name, meta),
    meta: { action: "Save metadata" },
    onSuccess: (saved) => {
      client.setQueryData(["project", p.name], saved);
      void client.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      toast("Metadata saved", { description: `projects/${p.name}/README.md` });
    },
  });
  const links = Object.entries(p.links)
    .map(([k, v]) => `${k} ${v}`)
    .join("\n");
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Pencil /> Edit metadata
      </Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        id="edit"
        title="Edit metadata"
        description={`The front matter of projects/${p.name}/README.md. Lists are comma-separated; the README's text is kept.`}
        pending={save.isPending}
        submit="Save"
        onSubmit={(form) =>
          save.mutate({
            title: text(form, "title"),
            status: text(form, "status") as ProjectMeta["status"],
            summary: text(form, "summary"),
            tags: list(form, "tags"),
            links: Object.fromEntries(
              text(form, "links")
                .split("\n")
                .map((line) => line.trim().split(/\s+/))
                .filter((bits) => bits.length >= 2)
                .map((bits) => [bits[0], bits.slice(1).join(" ")]),
            ),
            models: list(form, "models"),
            datasets: list(form, "datasets"),
            benchmarks: list(form, "benchmarks"),
          })
        }
      >
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <Label text="Title">
            <Input name="title" defaultValue={p.title} autoComplete="off" />
          </Label>
          <Label text="Status">
            <StatusSelect value={p.status} />
          </Label>
        </div>
        <Label text="Summary, one line">
          <Input name="summary" defaultValue={p.summary} autoComplete="off" />
        </Label>
        <Label text="Links, one a line: name URL">
          <Textarea
            name="links"
            defaultValue={links}
            rows={3}
            placeholder="repo https://github.com/me/project"
            className="font-mono text-xs"
          />
        </Label>
        <Label text="Models">
          <Input name="models" defaultValue={p.models.join(", ")} className="font-mono" />
        </Label>
        <Label text="Datasets">
          <Input name="datasets" defaultValue={p.datasets.join(", ")} className="font-mono" />
        </Label>
        <Label text="Benchmarks">
          <Input name="benchmarks" defaultValue={p.benchmarks.join(", ")} className="font-mono" />
        </Label>
        <Label text="Tags">
          <Input name="tags" defaultValue={p.tags.join(", ")} />
        </Label>
      </FormDialog>
    </>
  );
}
