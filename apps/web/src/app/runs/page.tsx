import { ListTree } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Runs" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/runs/")} phase={2} />
      <section className="mx-auto max-w-5xl px-6 py-8">
        <EmptyState
          icon={ListTree}
          title="No runs yet"
          body="Eval logs, analyses and training runs appear here as soon as they are written."
          command="inspect eval experiments/<name>/task.py --model hf/Qwen/Qwen2.5-1.5B-Instruct"
        />
      </section>
    </>
  );
}
