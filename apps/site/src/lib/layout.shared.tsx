import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";

import { Mark } from "@/components/mark";
import { appName, appUrl, repoUrl } from "./shared";

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <span className="flex items-center gap-2 font-semibold tracking-tight">
          <Mark className="size-5" />
          {appName}
        </span>
      ),
    },
    githubUrl: repoUrl,
    links: [
      { text: "Docs", url: "/docs" },
      ...(appUrl ? [{ text: "App", url: appUrl, external: true }] : []),
    ],
  };
}
