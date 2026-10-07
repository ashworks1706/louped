import { CopyButton } from "@/components/copy-button";
import { ScoreCell } from "@/components/metric";
import { part, partId } from "@/components/parts";
import { Term } from "@/components/term";
import { Badge } from "@/components/ui/badge";
import type { ModelInput, SampleDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

const ROLE_STYLE: Record<string, string> = {
  user: "bg-muted/60 border",
  system: "border border-dashed text-muted-foreground",
  tool: "border bg-muted/30 font-mono text-[13px]",
  assistant: "",
};

/** One sample's conversation, turn by turn, with its scores underneath. */
export function Transcript({
  sample,
  compact = false,
}: {
  sample: SampleDetail;
  compact?: boolean;
}) {
  return (
    <div className="flex flex-col gap-5">
      <ol className="flex flex-col gap-4">
        {sample.messages.map((m, i) => (
          <li key={i} className="flex flex-col gap-1.5">
            <span className="text-muted-foreground flex items-baseline gap-1.5 text-[11px] font-medium tracking-wide uppercase">
              {m.role}
              {m.function && (
                <span className="font-mono tracking-normal normal-case">· {m.function}</span>
              )}
            </span>
            <div
              className={cn(
                "rounded-lg text-sm leading-relaxed whitespace-pre-wrap",
                m.role === "assistant" ? "px-0.5" : "px-3 py-2",
                ROLE_STYLE[m.role] ?? "border px-3 py-2",
                m.error && "border-negative/40",
              )}
            >
              {m.error ? (
                <span className="text-negative">{m.error}</span>
              ) : (
                m.text ||
                (m.tool_calls.length === 0 && (
                  <span className="text-muted-foreground italic">(no text)</span>
                ))
              )}
              {m.tool_calls.map((c, j) => (
                <div
                  key={j}
                  data-testid="tool-call"
                  className="bg-muted/40 mt-2 flex flex-col gap-1 rounded-md border px-3 py-2 font-mono text-xs first:mt-0"
                >
                  <span className="text-foreground font-medium">{c.function}</span>
                  {c.parse_error ? (
                    <span className="text-negative whitespace-pre-wrap">{c.parse_error}</span>
                  ) : (
                    <pre className="text-muted-foreground overflow-x-auto">{c.arguments}</pre>
                  )}
                </div>
              ))}
            </div>
          </li>
        ))}
      </ol>
      {!compact && (
        <div className="flex flex-col gap-2 border-t pt-4">
          <span className="text-muted-foreground text-xs font-medium">Target</span>
          <p className="font-mono text-sm">{sample.target || "—"}</p>
        </div>
      )}
      {!compact && sample.inputs?.length ? <ModelInputs inputs={sample.inputs} /> : null}
      <div className="flex flex-col divide-y rounded-lg border">
        {sample.scores.map((s) => (
          <div
            key={s.name}
            className="flex items-start gap-3 px-3 py-2.5 text-sm"
            {...part(partId("sample/score", s.name))}
          >
            <ScoreCell value={s.value} />
            <div className="min-w-0 flex-1">
              <div className="font-medium">{s.name}</div>
              {s.explanation && <p className="text-muted-foreground">{s.explanation}</p>}
              {s.read_by && (
                <p className="text-muted-foreground flex flex-wrap items-center gap-x-1.5 text-xs">
                  <Term k="readBy">read by</Term>
                  <span className="text-foreground font-mono">{s.read_by}</span>
                  {s.matched != null && <span className="truncate font-mono">“{s.matched}”</span>}
                </p>
              )}
            </div>
            <Badge variant="outline" className="font-mono">
              {s.raw}
            </Badge>
          </div>
        ))}
      </div>
      {sample.error && (
        <pre className="border-negative/30 bg-negative/5 text-negative overflow-x-auto rounded-lg border p-3 text-xs whitespace-pre-wrap">
          {sample.error}
        </pre>
      )}
    </div>
  );
}

/** What each model call read, as fed: the chat template applied, special tokens shaded. */
function ModelInputs({ inputs }: { inputs: ModelInput[] }) {
  return (
    <section className="flex flex-col gap-2 border-t pt-4">
      <span {...part("sample/model-input")}>
        <Term k="modelInput" className="text-muted-foreground text-xs font-medium">
          Model input
        </Term>
      </span>
      {inputs.map((m, i) => (
        <div
          key={i}
          className="flex flex-col gap-1.5"
          {...part(partId("sample/input", String(i + 1)))}
        >
          <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 text-xs">
            {inputs.length > 1 && (
              <span>
                Call {i + 1} of {inputs.length}
              </span>
            )}
            <span className="font-mono">{m.model}</span>
            {m.text != null && (
              <>
                <span className="font-mono tabular-nums">{m.tokens} tokens</span>
                <span title={`Chat template of ${m.tokenizer}: first 12 hex of its sha256`}>
                  template <span className="text-foreground font-mono">{m.chat_template}</span>
                </span>
                <span className="ml-auto">
                  <CopyButton text={m.text} label="Copy model input" />
                </span>
              </>
            )}
          </div>
          {m.text == null ? (
            <p className="text-muted-foreground rounded-md border border-dashed px-3 py-2 text-xs">
              The rendered input is not known for this provider: it applies its own chat template
              and does not report the text. Only louped/ models report it.
            </p>
          ) : (
            <pre className="bg-muted/30 max-h-80 overflow-y-auto rounded-md border px-3 py-2 font-mono text-xs leading-relaxed whitespace-pre-wrap">
              <Rendered text={m.text} specials={m.special_tokens ?? []} />
            </pre>
          )}
        </div>
      ))}
    </section>
  );
}

/** The text with each special token as a muted chip. */
function Rendered({ text, specials }: { text: string; specials: string[] }) {
  if (specials.length === 0) return text;
  const escaped = specials.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  // specials come longest first, so a token inside a longer one is not split out of it
  const pieces = text.split(new RegExp(`(${escaped.join("|")})`));
  const special = new Set(specials);
  return pieces.map((p, i) =>
    special.has(p) ? (
      <span key={i} className="bg-muted text-muted-foreground rounded-sm px-0.5">
        {p}
      </span>
    ) : (
      p
    ),
  );
}
