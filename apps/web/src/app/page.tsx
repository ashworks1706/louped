import { PageHeader } from "@/components/page-header";
import { RunsList } from "@/components/runs-list";
import { navItem } from "@/lib/nav";

export default function Home() {
  return (
    <>
      <PageHeader item={navItem("/")} />
      <section className="mx-auto max-w-6xl px-6 py-8">
        <RunsList limit={10} compact />
      </section>
    </>
  );
}
