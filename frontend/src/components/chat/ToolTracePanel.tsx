import { memo, useMemo, useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, Clock, Copy, Loader2, Wrench, X, XCircle } from "lucide-react";
import type { SessionTraceEntry } from "@/lib/api";
import { localizeToolName } from "@/lib/tools";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  loading?: boolean;
  entries: SessionTraceEntry[];
  onClose: () => void;
}

interface Step {
  key: string;
  type: "tool" | "skill";
  tool: string;
  skill?: string;
  iter?: number | null;
  ts?: number | null;
  status: "running" | "ok" | "error";
  elapsed_ms?: number | null;
  args?: Record<string, unknown> | null;
  result?: string | null;
  preview?: string | null;
}

function pretty(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatTime(ts?: number | null): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleTimeString();
}

function buildSteps(entries: SessionTraceEntry[]): Step[] {
  const byCall = new Map<string, Step>();
  const loose: Step[] = [];
  entries.forEach((entry, index) => {
    const callId = entry.call_id || `entry-${index}`;
    const isSkill = entry.type.startsWith("skill") || entry.tool === "load_skill";
    if (entry.type.endsWith("_call")) {
      const step: Step = {
        key: callId,
        type: isSkill ? "skill" : "tool",
        tool: entry.tool || "unknown",
        skill: entry.skill_name || undefined,
        iter: entry.iter,
        ts: entry.ts,
        status: "running",
        args: entry.args,
      };
      byCall.set(callId, step);
      loose.push(step);
      return;
    }
    if (entry.type.endsWith("_result")) {
      const step = byCall.get(callId) || {
        key: callId,
        type: isSkill ? "skill" : "tool",
        tool: entry.tool || "unknown",
        skill: entry.skill_name || undefined,
        status: "running",
      } as Step;
      step.status = entry.status === "ok" ? "ok" : "error";
      step.elapsed_ms = entry.elapsed_ms;
      step.result = entry.result || entry.preview || "";
      step.preview = entry.preview || "";
      step.args = step.args || entry.args;
      step.iter = step.iter ?? entry.iter;
      step.ts = step.ts ?? entry.ts;
      if (!byCall.has(callId)) {
        byCall.set(callId, step);
        loose.push(step);
      }
    }
  });
  return loose;
}

export const ToolTracePanel = memo(function ToolTracePanel({ open, loading = false, entries, onClose }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const steps = useMemo(() => buildSteps(entries), [entries]);
  const toolCount = steps.filter((s) => s.type === "tool").length;
  const skillCount = steps.filter((s) => s.type === "skill").length;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-background/35 backdrop-blur-sm">
      <button className="flex-1 cursor-default" onClick={onClose} aria-label="Close trace panel" />
      <aside className="flex h-full w-full max-w-2xl flex-col border-l bg-background shadow-xl">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold">工具与 Skill 记录</h2>
            <p className="text-xs text-muted-foreground">
              {loading ? "加载中..." : `${toolCount} 个工具调用 · ${skillCount} 个 Skill 调用`}
            </p>
          </div>
          <button onClick={onClose} className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {loading ? (
            <div className="flex items-center gap-2 rounded-lg border p-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在读取完整 trace...
            </div>
          ) : steps.length === 0 ? (
            <div className="rounded-lg border p-4 text-sm text-muted-foreground">
              当前会话还没有工具或 Skill 调用记录。
            </div>
          ) : (
            <div className="space-y-2">
              {steps.map((step, index) => {
                const isOpen = !!expanded[step.key];
                const label = step.type === "skill"
                  ? `load_skill(${step.skill || "unknown"})`
                  : localizeToolName(step.tool);
                return (
                  <div key={`${step.key}-${index}`} className="rounded-lg border bg-card">
                    <button
                      onClick={() => setExpanded((prev) => ({ ...prev, [step.key]: !isOpen }))}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-muted/40"
                    >
                      {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                      {step.status === "running" ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                      ) : step.status === "error" ? (
                        <XCircle className="h-3.5 w-3.5 text-danger" />
                      ) : (
                        <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                      )}
                      <Wrench className={cn("h-3.5 w-3.5", step.type === "skill" ? "text-purple-500" : "text-muted-foreground")} />
                      <span className="min-w-0 flex-1 truncate font-medium">{label}</span>
                      {step.iter != null && <span className="text-muted-foreground">iter {step.iter}</span>}
                      {step.elapsed_ms != null && (
                        <span className="inline-flex items-center gap-1 text-muted-foreground">
                          <Clock className="h-3 w-3" />
                          {(step.elapsed_ms / 1000).toFixed(1)}s
                        </span>
                      )}
                      {step.ts && <span className="text-muted-foreground">{formatTime(step.ts)}</span>}
                    </button>

                    {isOpen && (
                      <div className="space-y-3 border-t px-3 py-3">
                        {step.args && Object.keys(step.args).length > 0 && (
                          <TraceBlock title="参数" value={pretty(step.args)} />
                        )}
                        {(step.result || step.preview) && (
                          <TraceBlock title="完整结果" value={step.result || step.preview || ""} />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
});

function TraceBlock({ title, value }: { title: string; value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] font-medium text-muted-foreground">{title}</span>
        <button
          onClick={() => {
            navigator.clipboard.writeText(value);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Copy className="h-3 w-3" />
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-muted/45 p-2 text-[11px] leading-relaxed text-foreground/85">
        {value}
      </pre>
    </div>
  );
}
