import Link from "next/link";

import { Mark } from "@/components/mark";
import { appName, appUrl, docsRoute, repoUrl } from "@/lib/shared";

export default function Layout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <Mark className="size-5" />
          {appName}
        </Link>
        <nav className="text-fd-muted-foreground flex items-center gap-6 text-sm">
          <Link href={docsRoute} className="hover:text-fd-foreground">
            Docs
          </Link>
          <a href={repoUrl} className="hover:text-fd-foreground">
            GitHub
          </a>
          {appUrl ? (
            <a
              href={appUrl}
              className="bg-fd-primary text-fd-primary-foreground rounded-md px-3 py-1.5 font-medium hover:opacity-90"
            >
              Open app
            </a>
          ) : null}
        </nav>
      </header>
      {children}
    </div>
  );
}
