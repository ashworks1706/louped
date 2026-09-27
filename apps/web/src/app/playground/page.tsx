import { MessageSquareText } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export const metadata: Metadata = { title: "Playground" };

export default function Page() {
  return (
    <>
      <PageHeader item={navItem("/playground/")} phase={4} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <EmptyState
          icon={MessageSquareText}
          title="No model loaded"
          body="Chat with a base model and a steered one side by side, with the layer and strength as sliders."
          command="loupe serve --model Qwen/Qwen2.5-1.5B-Instruct"
        />
      </section>
    </>
  );
}
