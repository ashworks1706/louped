import { createGetUrl } from "fumadocs-core/source";

export const appName = "loupe";
export const tagline = "Look inside the model you're testing.";
export const docsRoute = "/docs";
export const docsContentRoute = "/llms.mdx/docs";
export const repoUrl = "https://github.com/ashworks1706/loupe";
/** Set when the site is served under a path, such as a GitHub Pages project site. */
export const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
/** The hosted read-only UI; unset until a demo is deployed, and then the App link appears. */
export const appUrl = process.env.NEXT_PUBLIC_APP_URL ?? "";

const getContentUrl = createGetUrl(docsContentRoute);

export function getPageMarkdownUrl(page: { slugs: string[]; locale?: string }) {
  const segments = [...page.slugs, "content.md"];
  return { segments, url: getContentUrl(segments, page.locale) };
}
