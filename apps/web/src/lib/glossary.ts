/** What a term means, for the ? beside it. One place, so a word reads the same on every page. */
export const GLOSSARY = {
  // vectors
  layer:
    "The transformer layer whose residual stream the vector was read from. Steering adds it back at this layer.",
  method:
    "How the vector was found. diff-in-means: average activation on prompts with the concept minus prompts without. logistic-probe: the weights of a linear classifier for the concept. sae-decoder: one sparse-autoencoder feature's direction.",
  norm: "The vector's length. Steering adds α times the vector, so with a large norm even α = 1 is a strong push.",
  dim: "Its number of entries: the model's hidden size.",
  model: "The model the vector belongs to. It only works on that model's activations.",
  source: "The run that saved the vector, with the figures that chose its layer.",
  // the Hub
  downloads: "Downloads on the Hugging Face Hub in the last 30 days.",
  likes: "People who liked it on the Hugging Face Hub.",
  params:
    "Parameters in the model's safetensors files, as the Hub counts them. Empty when it has none.",
  gated:
    "Its owner asks people to accept terms first. Ask for access on its Hub page, then use a token of that account.",
  upvotes: "Votes for the paper on the Hugging Face Hub's papers page.",
  hubSize: "Bytes the repository takes on the Hub: every file, every format.",
  // runs
  kind: "eval: a model scored on a task. analysis: figures from a script, such as patching or a sweep. training: fine-tuning, with its curves.",
  headline: "The run's first reported metric, at its final value. Open the run for all of them.",
  // compare
  delta: "B minus A: the changed run's score minus the baseline's, averaged over samples.",
  ratio: "B ÷ A. For a cost, under 1 is a saving; for throughput, over 1 is a speed-up.",
  n: "Samples both runs scored. Only those are compared.",
  interval:
    "95% paired bootstrap interval of B − A. When it excludes zero, the difference is unlikely to be noise.",
  moved: "Samples where B scored higher or lower than A. Click a count to read them.",
  // samples
  modelInput:
    "The exact text the model read: the conversation after the tokenizer's chat template, with the special tokens the tokenizer adds. Special tokens are shaded. The template hash is the first 12 hex digits of the template's sha256: two calls with the same hash used the same template. Only louped/ models report it; for another provider louped does not guess.",
  readBy:
    "The rule that read the verdict from the reply's text, and the text it matched. none: no rule matched, so the score is the scorer's default. Check it when a score looks wrong.",
  disagree:
    "Samples where two scorers that read a verdict (they record their rule, or grade C/I) gave different values. A misread answer shows up here; on a task whose scorers ask different questions, a difference can be the result itself.",
  // items
  wilson:
    "95% Wilson interval of a rate k/n. Unlike k/n ± 1.96·SE it stays inside 0–100% and holds up at small n and extreme rates, so a pilot's uncertainty reads honestly.",
  transition:
    "Items that changed from the reference: 1→0 counts items right in the reference and wrong here, out of those right in the reference; 0→1 the reverse. The reference fixes both denominators, so every condition is read on the same items.",
  // training sets
  chosen_in_prompt:
    "The chosen reply, lowercased with spaces collapsed, is already in the prompt (any turn, the system turn too). Training on it teaches the model to copy its input. 20% or more of a set warns.",
  length_only:
    "The two replies differ mostly in length: the longer has 1.5 times the words or more, and the shorter is its start or shares 80% or more of its words. The model learns length, not content. DPO only.",
  provenance:
    "How the chosen reply was picked: the source and review louped recorded when it built the set. unknown: louped did not build the set (louped builds no DPO pairs).",
  // degenerate replies
  repeat:
    "Share of replies that say again what an earlier assistant turn of the same conversation said: the same text, or 90% the same words.",
  echo: "Share of replies that copy the system prompt (20 words in a row, or all of a short one) or chat-template text (<|im_start|>, [INST], or Assistant: at the start).",
  loop: "Share of replies that repeat themselves: one run of 8 words occurs 3 times or more.",
  // attribution graphs
  influence:
    "The node's share of the effect on the output, directly and through every later node. The output starts with its probability; each node passes what it gets to its inputs in proportion to their weights.",
  keep_nodes:
    "Keep the strongest nodes until they carry this share of the influence on the output. Lower shows the core of the circuit; higher shows more of it.",
  keep_edges:
    "Of the edges between kept nodes, keep the strongest until they carry this share of the influence.",
  edge_weight:
    "The direct effect of one node on another: positive (green) pushes it up, negative (red) pushes it down.",
  error_node:
    "What the transcoder does not explain at that layer and position: a dashed diamond. A strong one means part of the circuit is not in the features.",
  activation: "How strongly the feature fires at its token position.",
} as const;

export type Term = keyof typeof GLOSSARY;

/** What a scorer measures, by the scorer half of a scorer/metric key. */
const SCORERS: Record<string, string> = {
  refusal: "Share of replies that refuse.",
  held: "Share of answers that stayed right after pushback.",
  correct_first: "Share of first answers that were right.",
  expectations: "Share of each case's expectations the reply met.",
  accuracy: "Share of answers that were right.",
  latency: "Seconds per reply. Lower is better.",
  time_to_first_token: "Seconds before the first token. Lower is better.",
  tokens_per_second: "Tokens generated per second. Higher is better.",
  peak_memory: "Most GPU memory in use, in MiB. Lower is better.",
  tool_calls: "Tool calls per sample.",
  tool_errors: "Share of tool calls that errored. Lower is better.",
  called: "Share of samples that called the tool.",
  grounded: "Share of answers that used a tool's output.",
  recall: "Share of the gold passages found in the top k retrieved.",
  faithful: "How likely the retrieved text supports the answer.",
  b_wins:
    "Share of pairs a judge model preferred B, averaged over both answer orders. 0.5 is no preference.",
  consistent: "Share of pairs where the judge picked the same winner in both orders.",
  parsed: "Share of the judge's replies that ended in a verdict; the rest count as ties.",
};

/** How it is aggregated over samples, by the metric half. */
const AGGREGATES: Record<string, string> = {
  mean: "Averaged over samples.",
  accuracy: "Share of samples scored correct.",
  stderr: "Standard error of the mean.",
};

/** What a scorer/metric key measures, or null for one louped does not know. */
export function metricMeaning(key: string): string | null {
  const [scorer, metric] = key.split("/");
  const what = SCORERS[scorer];
  if (!what) return null;
  const how = metric ? AGGREGATES[metric] : undefined;
  return how ? `${what} ${how}` : what;
}
