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
  // runs
  kind: "eval: a model scored on a task. analysis: figures from a script, such as patching or a sweep. training: fine-tuning, with its curves.",
  headline: "The run's last logged metric. Open the run for all of them.",
  // compare
  delta: "B minus A: the changed run's score minus the baseline's, averaged over samples.",
  ratio: "B ÷ A. For a cost, under 1 is a saving; for throughput, over 1 is a speed-up.",
  n: "Samples both runs scored. Only those are compared.",
  interval:
    "95% paired bootstrap interval of B − A. When it excludes zero, the difference is unlikely to be noise.",
  moved: "Samples where B scored higher or lower than A. Click a count to read them.",
  // items
  wilson:
    "95% Wilson interval of a rate k/n. Unlike k/n ± 1.96·SE it stays inside 0–100% and holds up at small n and extreme rates, so a pilot's uncertainty reads honestly.",
  transition:
    "Items that changed from the reference: 1→0 counts items right in the reference and wrong here, out of those right in the reference; 0→1 the reverse. The reference fixes both denominators, so every condition is read on the same items.",
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
  recall: "Share of the gold passages among those retrieved.",
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

/** What a scorer/metric key measures, or null for one loupe does not know. */
export function metricMeaning(key: string): string | null {
  const [scorer, metric] = key.split("/");
  const what = SCORERS[scorer];
  if (!what) return null;
  const how = metric ? AGGREGATES[metric] : undefined;
  return how ? `${what} ${how}` : what;
}
