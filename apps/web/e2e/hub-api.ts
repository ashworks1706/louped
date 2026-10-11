import type { Page } from "@playwright/test";

// The Hugging Face Hub over a mocked API: a signed-in account, a gated model, a paper.

const qwen = {
  kind: "models",
  id: "Qwen/Qwen2.5-0.5B-Instruct",
  url: "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct",
  downloads: 1_200_000,
  likes: 340,
  task: "text-generation",
  library: "transformers",
  gated: true,
  private: false,
  updated: "2026-09-01T00:00:00Z",
  params: 494_000_000,
  title: null,
  authors: [],
  upvotes: null,
};
const paper = {
  ...qwen,
  kind: "papers",
  id: "2310.13548",
  url: "https://huggingface.co/papers/2310.13548",
  downloads: null,
  likes: null,
  task: null,
  library: null,
  gated: false,
  params: null,
  title: "Towards Understanding Sycophancy in Language Models",
  authors: ["Mrinank Sharma", "Meg Tong"],
  upvotes: 12,
};

export async function mockHub(page: Page) {
  const json = (glob: string, body: unknown) => page.route(glob, (r) => r.fulfill({ json: body }));
  await json("**/api/hub/me", { token: true, name: "ash", avatar: null, error: null });
  await json("**/api/hub/added", { models: [qwen.id], embeddings: [], datasets: [] });
  await page.route("**/api/hub/search?*", (r) =>
    r.fulfill({ json: r.request().url().includes("kind=papers") ? [paper] : [qwen] }),
  );
  await page.route("**/api/hub/info?*", (r) => {
    const papers = r.request().url().includes("kind=papers");
    return r.fulfill({
      json: papers
        ? { ...paper, card: null, license: null, tags: [], size: null, files: null,
            summary: "Models agree with their users.",
            links: { arxiv: "https://arxiv.org/abs/2310.13548" } } // prettier-ignore
        : { ...qwen, card: "# Qwen\n\nA small model.", license: "apache-2.0",
            tags: ["text-generation"], size: 988_000_000, files: 10, summary: null,
            links: {} }, // prettier-ignore
    });
  });
}
