import { ScoreCell } from "@/components/metric";
import { Badge } from "@/components/ui/badge";
import type { SampleDetail } from "@/lib/api";
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
      <div className="flex flex-col divide-y rounded-lg border">
        {sample.scores.map((s) => (
          <div key={s.name} className="flex items-start gap-3 px-3 py-2.5 text-sm">
            <ScoreCell value={s.value} />
            <div className="min-w-0 flex-1">
              <div className="font-medium">{s.name}</div>
              {s.explanation && <p className="text-muted-foreground">{s.explanation}</p>}
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
