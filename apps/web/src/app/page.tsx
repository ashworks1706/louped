import { HomeBlocks } from "@/components/home-overview";
import { PageHeader } from "@/components/page-header";
import { navItem } from "@/lib/nav";

export default function Home() {
  return (
    <>
      <PageHeader item={navItem("/")} />
      <div className="mx-auto max-w-6xl px-6 py-8">
        <HomeBlocks />
      </div>
    </>
  );
}
