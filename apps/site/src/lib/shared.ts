import { createGetUrl } from "fumadocs-core/source";

export const appName = "loupe";
export const tagline = "A testbed for LLM behavior and efficiency.";
export const docsRoute = "/docs";
export const docsContentRoute = "/llms.mdx/docs";
export const repoUrl = "https://github.com/ashworks1706/loupe";
/** The hosted read-only app (app.<domain>); unset until it is deployed, and then its links appear. */
export const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "";

const getContentUrl = createGetUrl(docsContentRoute);

export function getPageMarkdownUrl(page: { slugs: string[]; locale?: string }) {
  const segments = [...page.slugs, "content.md"];
  return { segments, url: getContentUrl(segments, page.locale) };
}
