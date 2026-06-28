import { useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness, CheckCircle2, ClipboardList, Eye, FileText, ImageUp, LineChart, Loader2, Pencil, Plus, RefreshCw, Save, Target, Trash2, TriangleAlert, X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type PortfolioDashboard, type PortfolioDecision, type PortfolioInstrument, type PortfolioPosition, type PortfolioResearchReport, type PortfolioRuleEventPage, type PortfolioTrackingRule, type PortfolioWatchlistItem, type PositionImportItemPatch, type PositionImportJob } from "@/lib/api";
import { cn } from "@/lib/utils";

const numberFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const pctFmt = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 2 });

function money(value: number | null | undefined) {
  return numberFmt.format(value ?? 0);
}

function timeText(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : "-";
}

function compactJson(value: unknown) {
  try {
    return JSON.stringify(value ?? {});
  } catch {
    return "{}";
  }
}

function parseJsonInput(value: string): Record<string, unknown> {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON 必须是对象");
  }
  return parsed as Record<string, unknown>;
}

function percentInputToWeight(value: string): number | null {
  if (!value.trim()) return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return num > 1 ? num / 100 : num;
}

function weightToPercentInput(value: number | null | undefined): string {
  return value == null ? "" : String(Number((value * 100).toFixed(4)));
}

function optionalNumberInput(value: string): number | null {
  if (!value.trim()) return null;
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("mt-2 text-2xl font-semibold", tone === "up" && "text-success", tone === "down" && "text-danger")}>{value}</div>
    </div>
  );
}

function EmptyRow({ text, colSpan }: { text: string; colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-8 text-center text-sm text-muted-foreground">{text}</td>
    </tr>
  );
}

export function InvestmentWorkspace() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<PortfolioDashboard | null>(null);
  const [instruments, setInstruments] = useState<PortfolioInstrument[]>([]);
  const [watchlist, setWatchlist] = useState<PortfolioWatchlistItem[]>([]);
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [reports, setReports] = useState<PortfolioResearchReport[]>([]);
  const [decisions, setDecisions] = useState<PortfolioDecision[]>([]);
  const [trackingRules, setTrackingRules] = useState<PortfolioTrackingRule[]>([]);
  const [ruleEvents, setRuleEvents] = useState<PortfolioRuleEventPage | null>(null);
  const [ruleEventOffset, setRuleEventOffset] = useState(0);
  const [importJobs, setImportJobs] = useState<PositionImportJob[]>([]);
  const [activeImport, setActiveImport] = useState<PositionImportJob | null>(null);
  const [uploading, setUploading] = useState(false);
  const [editingInstrumentId, setEditingInstrumentId] = useState<string | null>(null);
  const [instrumentDraft, setInstrumentDraft] = useState<Record<string, string>>({});
  const [editingWatchlistId, setEditingWatchlistId] = useState<string | null>(null);
  const [watchlistDraft, setWatchlistDraft] = useState<Record<string, string>>({});
  const [editingPositionId, setEditingPositionId] = useState<string | null>(null);
  const [positionDraft, setPositionDraft] = useState<Record<string, string>>({});
  const [instrumentForm, setInstrumentForm] = useState({ symbol: "", name: "", market: "US", asset_class: "equity", currency: "USD", tags: "", thesis: "" });
  const [positionForm, setPositionForm] = useState({ instrument_id: "", quantity: "", avg_cost: "", target_weight: "", notes: "" });
  const [decisionForm, setDecisionForm] = useState({ instrument_id: "", decision_type: "watch", title: "", rationale: "" });
  const [ruleForm, setRuleForm] = useState({ instrument_id: "", name: "", rule_type: "price", cadence: "daily", condition: "{\"price_above\": 0}", action: "{\"research\": \"quick_update\"}", is_enabled: true });
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [ruleDraft, setRuleDraft] = useState<Record<string, string>>({});

  const selectedInstrument = useMemo(
    () => instruments.find((item) => item.id === positionForm.instrument_id),
    [instruments, positionForm.instrument_id],
  );
  const watchlistedInstrumentIds = useMemo(
    () => new Set(watchlist.map((item) => item.instrument_id)),
    [watchlist],
  );

  const load = async () => {
    setError(null);
    setLoading(true);
    try {
      const [dash, inst, watch, pos, reps, decs, rules, events, jobs] = await Promise.all([
        api.portfolio.dashboard(),
        api.portfolio.listInstruments(),
        api.portfolio.listWatchlist(),
        api.portfolio.listPositions(),
        api.portfolio.listResearchReports(),
        api.portfolio.listDecisions(),
        api.portfolio.listTrackingRules(),
        api.portfolio.listRuleEvents(ruleEventOffset, 10),
        api.portfolio.listImports(),
      ]);
      setDashboard(dash);
      setInstruments(inst);
      setWatchlist(watch);
      setPositions(pos);
      setReports(reps);
      setDecisions(decs);
      setTrackingRules(rules);
      setRuleEvents(events);
      setImportJobs(jobs);
      setActiveImport((prev) => prev ? jobs.find((job) => job.id === prev.id) ?? prev : jobs[0] ?? null);
      if (!positionForm.instrument_id && inst.length) {
        setPositionForm((prev) => ({ ...prev, instrument_id: inst[0].id }));
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "投资工作台数据加载失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => {
    api.portfolio.listRuleEvents(ruleEventOffset, 10).then(setRuleEvents).catch(() => undefined);
  }, [ruleEventOffset]);

  const createInstrument = async () => {
    if (!instrumentForm.symbol.trim() || !instrumentForm.name.trim()) return;
    setSaving(true);
    try {
      const created = await api.portfolio.createInstrument({
        ...instrumentForm,
        symbol: instrumentForm.symbol.trim().toUpperCase(),
        name: instrumentForm.name.trim(),
        tags: instrumentForm.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        thesis: instrumentForm.thesis || null,
      });
      setInstrumentForm({ symbol: "", name: "", market: "US", asset_class: "equity", currency: "USD", tags: "", thesis: "" });
      setPositionForm((prev) => ({ ...prev, instrument_id: created.id }));
      await api.portfolio.createWatchlistItem({ instrument_id: created.id, priority: 3, status: "watching" }).catch(() => undefined);
      toast.success("标的已加入工作台");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "新增标的失败");
    } finally {
      setSaving(false);
    }
  };

  const createPosition = async () => {
    if (!positionForm.instrument_id || !positionForm.quantity || !positionForm.avg_cost) return;
    setSaving(true);
    try {
      await api.portfolio.createPosition({
        instrument_id: positionForm.instrument_id,
        quantity: Number(positionForm.quantity),
        avg_cost: Number(positionForm.avg_cost),
        target_weight: percentInputToWeight(positionForm.target_weight),
        notes: positionForm.notes,
      });
      setPositionForm((prev) => ({ ...prev, quantity: "", avg_cost: "", target_weight: "", notes: "" }));
      toast.success("持仓已保存");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "保存持仓失败");
    } finally {
      setSaving(false);
    }
  };

  const startEditInstrument = (item: PortfolioInstrument) => {
    setEditingInstrumentId(item.id);
    setInstrumentDraft({
      symbol: item.symbol,
      name: item.name,
      market: item.market,
      tags: item.tags?.join(", ") || "",
      thesis: item.thesis || "",
    });
  };

  const saveInstrument = async (id: string) => {
    setSaving(true);
    try {
      await api.portfolio.updateInstrument(id, {
        symbol: instrumentDraft.symbol?.trim().toUpperCase(),
        name: instrumentDraft.name?.trim(),
        market: instrumentDraft.market?.trim().toUpperCase(),
        tags: (instrumentDraft.tags || "").split(",").map((tag) => tag.trim()).filter(Boolean),
        thesis: instrumentDraft.thesis || null,
      });
      setEditingInstrumentId(null);
      toast.success("标的已更新");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "更新标的失败");
    } finally {
      setSaving(false);
    }
  };

  const deleteInstrument = async (id: string) => {
    if (!window.confirm("确认删除/停用这个投资标的吗？")) return;
    setSaving(true);
    try {
      await api.portfolio.deleteInstrument(id);
      toast.success("标的已删除");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "删除标的失败");
    } finally {
      setSaving(false);
    }
  };

  const addToWatchlist = async (item: PortfolioInstrument) => {
    if (watchlistedInstrumentIds.has(item.id)) return;
    setSaving(true);
    try {
      await api.portfolio.createWatchlistItem({ instrument_id: item.id, priority: 3, status: "watching" });
      toast.success("已加入关注列表");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "加入关注列表失败");
    } finally {
      setSaving(false);
    }
  };

  const startEditWatchlist = (item: PortfolioWatchlistItem) => {
    setEditingWatchlistId(item.id);
    setWatchlistDraft({
      priority: String(item.priority ?? 3),
      status: item.status || "watching",
      target_price: item.target_price?.toString() || "",
      alert_price_low: item.alert_price_low?.toString() || "",
      alert_price_high: item.alert_price_high?.toString() || "",
      notes: item.notes || "",
    });
  };

  const saveWatchlist = async (id: string) => {
    setSaving(true);
    try {
      await api.portfolio.updateWatchlistItem(id, {
        priority: Number(watchlistDraft.priority || 3),
        status: watchlistDraft.status || "watching",
        target_price: watchlistDraft.target_price ? Number(watchlistDraft.target_price) : null,
        alert_price_low: watchlistDraft.alert_price_low ? Number(watchlistDraft.alert_price_low) : null,
        alert_price_high: watchlistDraft.alert_price_high ? Number(watchlistDraft.alert_price_high) : null,
        notes: watchlistDraft.notes || null,
      });
      setEditingWatchlistId(null);
      toast.success("关注项已更新");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "更新关注项失败");
    } finally {
      setSaving(false);
    }
  };

  const deleteWatchlist = async (id: string) => {
    if (!window.confirm("确认从关注列表移除吗？")) return;
    setSaving(true);
    try {
      await api.portfolio.deleteWatchlistItem(id);
      toast.success("关注项已删除");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "删除关注项失败");
    } finally {
      setSaving(false);
    }
  };

  const startEditPosition = (item: PortfolioPosition) => {
    setEditingPositionId(item.id);
    setPositionDraft({
      quantity: String(item.quantity ?? ""),
      avg_cost: String(item.avg_cost ?? ""),
      target_weight: weightToPercentInput(item.target_weight),
      stop_loss: item.stop_loss?.toString() || "",
      take_profit: item.take_profit?.toString() || "",
      notes: item.notes || "",
    });
  };

  const savePosition = async (id: string) => {
    setSaving(true);
    try {
      await api.portfolio.updatePosition(id, {
        quantity: Number(positionDraft.quantity || 0),
        avg_cost: Number(positionDraft.avg_cost || 0),
        target_weight: percentInputToWeight(positionDraft.target_weight),
        stop_loss: positionDraft.stop_loss ? Number(positionDraft.stop_loss) : null,
        take_profit: positionDraft.take_profit ? Number(positionDraft.take_profit) : null,
        notes: positionDraft.notes || null,
      });
      setEditingPositionId(null);
      toast.success("持仓已更新");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "更新持仓失败");
    } finally {
      setSaving(false);
    }
  };

  const deletePosition = async (id: string) => {
    if (!window.confirm("确认删除这个持仓吗？")) return;
    setSaving(true);
    try {
      await api.portfolio.deletePosition(id);
      toast.success("持仓已删除");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "删除持仓失败");
    } finally {
      setSaving(false);
    }
  };

  const createDecision = async () => {
    if (!decisionForm.title.trim() || !decisionForm.rationale.trim()) return;
    setSaving(true);
    try {
      await api.portfolio.createDecision({
        instrument_id: decisionForm.instrument_id || null,
        decision_type: decisionForm.decision_type,
        title: decisionForm.title.trim(),
        rationale: decisionForm.rationale.trim(),
      });
      setDecisionForm((prev) => ({ ...prev, title: "", rationale: "" }));
      toast.success("决策已记录");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "记录决策失败");
    } finally {
      setSaving(false);
    }
  };

  const createTrackingRule = async () => {
    if (!ruleForm.name.trim()) return;
    setSaving(true);
    try {
      await api.portfolio.createTrackingRule({
        instrument_id: ruleForm.instrument_id || null,
        name: ruleForm.name.trim(),
        rule_type: ruleForm.rule_type.trim() || "price",
        condition: parseJsonInput(ruleForm.condition),
        action: parseJsonInput(ruleForm.action),
        cadence: ruleForm.cadence.trim() || null,
        is_enabled: ruleForm.is_enabled,
      });
      setRuleForm((prev) => ({ ...prev, name: "" }));
      toast.success("自动跟踪规则已创建");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建规则失败");
    } finally {
      setSaving(false);
    }
  };

  const startEditRule = (item: PortfolioTrackingRule) => {
    setEditingRuleId(item.id);
    setRuleDraft({
      instrument_id: item.instrument_id || "",
      name: item.name,
      rule_type: item.rule_type,
      cadence: item.cadence || "",
      condition: JSON.stringify(item.condition || {}, null, 2),
      action: JSON.stringify(item.action || {}, null, 2),
      is_enabled: item.is_enabled ? "true" : "false",
    });
  };

  const saveTrackingRule = async (id: string) => {
    setSaving(true);
    try {
      await api.portfolio.updateTrackingRule(id, {
        instrument_id: ruleDraft.instrument_id || null,
        name: ruleDraft.name,
        rule_type: ruleDraft.rule_type,
        cadence: ruleDraft.cadence || null,
        condition: parseJsonInput(ruleDraft.condition || "{}"),
        action: parseJsonInput(ruleDraft.action || "{}"),
        is_enabled: ruleDraft.is_enabled !== "false",
      });
      setEditingRuleId(null);
      toast.success("规则已更新");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新规则失败");
    } finally {
      setSaving(false);
    }
  };

  const deleteTrackingRule = async (id: string) => {
    if (!window.confirm("确认删除这条自动跟踪规则吗？")) return;
    setSaving(true);
    try {
      await api.portfolio.deleteTrackingRule(id);
      toast.success("规则已删除");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "删除规则失败");
    } finally {
      setSaving(false);
    }
  };

  const uploadScreenshot = async (file: File | null) => {
    if (!file) return;
    setUploading(true);
    try {
      const job = await api.portfolio.uploadPositionScreenshot(file);
      setActiveImport(job);
      toast.success(job.status === "ready_to_save" ? "截图解析完成，可确认保存" : "截图已解析，请补全或核实缺失字段");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "截图上传失败");
    } finally {
      setUploading(false);
    }
  };

  const updateImportItem = (index: number, patch: PositionImportItemPatch) => {
    if (!activeImport) return;
    const next = {
      ...activeImport,
      items: activeImport.items.map((item, idx) => idx === index ? { ...item, ...patch } : item),
    };
    setActiveImport(next);
  };

  const addManualImportItem = () => {
    if (!activeImport) return;
    setActiveImport({
      ...activeImport,
      items: [
        ...activeImport.items,
        {
          id: `manual-${Date.now()}`,
          job_id: activeImport.id,
          row_index: activeImport.items.length + 1,
          symbol: "",
          name: "",
          market: "US",
          asset_class: "equity",
          currency: "USD",
          quantity: null,
          avg_cost: null,
          confidence: 1,
          field_confidence: {},
          missing_fields: ["symbol", "name", "quantity", "avg_cost"],
          warnings: [],
          status: "needs_review",
          raw: {},
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    });
  };

  const saveImportReview = async () => {
    if (!activeImport) return;
    setSaving(true);
    try {
      const job = await api.portfolio.updateImport(activeImport.id, {
        broker: activeImport.broker,
        account_name: activeImport.account_name,
        summary: activeImport.summary,
        items: activeImport.items.map((item) => ({
          symbol: item.symbol,
          name: item.name,
          market: item.market,
          asset_class: item.asset_class,
          currency: item.currency,
          quantity: item.quantity,
          available_quantity: item.available_quantity,
          avg_cost: item.avg_cost,
          cost_basis: item.cost_basis,
          market_price: item.market_price,
          market_value: item.market_value,
          unrealized_pnl: item.unrealized_pnl,
          unrealized_pnl_pct: item.unrealized_pnl_pct,
          status: item.status,
          source_text: item.source_text,
        })),
      });
      setActiveImport(job);
      toast.success(job.status === "ready_to_save" ? "完整性检查通过" : "已保存核实结果，仍有字段需要补全");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "保存核实结果失败");
    } finally {
      setSaving(false);
    }
  };

  const confirmImport = async () => {
    if (!activeImport) return;
    setSaving(true);
    try {
      await api.portfolio.confirmImport(activeImport.id, {
        account_name: activeImport.account_name,
        broker: activeImport.broker,
        overwrite_existing: true,
        save_price_snapshots: true,
      });
      toast.success("截图持仓已保存到投资工作台");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "确认保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-full bg-background p-6">
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <BriefcaseBusiness className="h-4 w-4" />
              Investment Workspace
            </div>
            <h1 className="mt-1 text-2xl font-semibold tracking-normal">投资工作台</h1>
          </div>
          <button onClick={load} className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted" disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            刷新
          </button>
        </div>

        {error ? (
          <div className="rounded-md border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
            {error}
          </div>
        ) : null}

        <div className="grid gap-3 md:grid-cols-4">
          <Stat label="总市值" value={money(dashboard?.total_market_value)} />
          <Stat label="总成本" value={money(dashboard?.total_cost_basis)} />
          <Stat label="未实现盈亏" value={money(dashboard?.total_unrealized_pnl)} tone={(dashboard?.total_unrealized_pnl ?? 0) >= 0 ? "up" : "down"} />
          <Stat label="标的 / 持仓" value={`${dashboard?.instruments ?? 0} / ${dashboard?.positions ?? 0}`} />
        </div>

        <section className="rounded-md border bg-card">
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <ClipboardList className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">当前持仓</h2>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr><th className="px-3 py-2 text-left">标的</th><th className="px-3 py-2 text-right">数量</th><th className="px-3 py-2 text-right">均价</th><th className="px-3 py-2 text-right">目标/实际</th><th className="px-3 py-2 text-right">偏离</th><th className="px-3 py-2 text-right">止损/止盈</th><th className="px-3 py-2 text-right">市值</th><th className="px-3 py-2 text-right">盈亏</th><th className="px-3 py-2 text-left">行情时间</th><th className="px-3 py-2 text-left">备注</th><th className="px-3 py-2 text-right">操作</th></tr>
              </thead>
              <tbody>
                {positions.length ? positions.map((item) => {
                  const editing = editingPositionId === item.id;
                  return (
                  <tr key={item.id} className="border-t align-top">
                    <td className="px-3 py-2 font-medium">
                      {item.instrument?.symbol ?? item.instrument_id}
                      <div className="text-xs font-normal text-muted-foreground">{item.instrument?.name}</div>
                    </td>
                    <td className="px-3 py-2 text-right">{editing ? <input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={positionDraft.quantity || ""} onChange={(e) => setPositionDraft({ ...positionDraft, quantity: e.target.value })} /> : money(item.quantity)}</td>
                    <td className="px-3 py-2 text-right">{editing ? <input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={positionDraft.avg_cost || ""} onChange={(e) => setPositionDraft({ ...positionDraft, avg_cost: e.target.value })} /> : money(item.avg_cost)}</td>
                    <td className="px-3 py-2 text-right">{editing ? <input className="w-20 rounded-md border bg-background px-2 py-1 text-right" title="输入百分比，例如 20 表示 20%" value={positionDraft.target_weight || ""} onChange={(e) => setPositionDraft({ ...positionDraft, target_weight: e.target.value })} /> : `${item.target_weight != null ? pctFmt.format(item.target_weight) : "-"} / ${item.actual_weight != null ? pctFmt.format(item.actual_weight) : "-"}`}</td>
                    <td className={cn("px-3 py-2 text-right", item.weight_drift != null && Math.abs(item.weight_drift) >= 0.02 ? "text-warning font-medium" : "text-muted-foreground")} title="实际权重 - 目标权重">{item.weight_drift != null ? pctFmt.format(item.weight_drift) : "-"}</td>
                    <td className="px-3 py-2 text-right">{editing ? <div className="flex justify-end gap-1"><input className="w-20 rounded-md border bg-background px-2 py-1 text-right" placeholder="止损" value={positionDraft.stop_loss || ""} onChange={(e) => setPositionDraft({ ...positionDraft, stop_loss: e.target.value })} /><input className="w-20 rounded-md border bg-background px-2 py-1 text-right" placeholder="止盈" value={positionDraft.take_profit || ""} onChange={(e) => setPositionDraft({ ...positionDraft, take_profit: e.target.value })} /></div> : `${item.stop_loss ?? "-"} / ${item.take_profit ?? "-"}`}</td>
                    <td className="px-3 py-2 text-right">{money(item.market_value)}</td>
                    <td className={cn("px-3 py-2 text-right", item.unrealized_pnl >= 0 ? "text-success" : "text-danger")}>{money(item.unrealized_pnl)} · {pctFmt.format(item.unrealized_pnl_pct || 0)}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{timeText(item.market_price_as_of)}<div>{item.market_price_source || "-"}</div></td>
                    <td className="max-w-[280px] px-3 py-2 text-muted-foreground">{editing ? <input className="w-full rounded-md border bg-background px-2 py-1" value={positionDraft.notes || ""} onChange={(e) => setPositionDraft({ ...positionDraft, notes: e.target.value })} /> : <span className="line-clamp-2">{item.notes || "-"}</span>}</td>
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1">
                        {editing ? (
                          <>
                            <button onClick={() => savePosition(item.id)} className="rounded-md border p-1.5 hover:bg-muted" title="保存"><Save className="h-4 w-4" /></button>
                            <button onClick={() => setEditingPositionId(null)} className="rounded-md border p-1.5 hover:bg-muted" title="取消"><X className="h-4 w-4" /></button>
                          </>
                        ) : (
                          <>
                            <button onClick={() => startEditPosition(item)} className="rounded-md border p-1.5 hover:bg-muted" title="编辑"><Pencil className="h-4 w-4" /></button>
                            <button onClick={() => deletePosition(item.id)} className="rounded-md border p-1.5 text-danger hover:bg-danger/10" title="删除"><Trash2 className="h-4 w-4" /></button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                )}) : <EmptyRow colSpan={11} text={loading ? "加载中..." : "暂无持仓"} />}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-md border bg-card">
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <Target className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">关注列表</h2>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr><th className="px-3 py-2 text-left">标的</th><th className="px-3 py-2 text-left">状态</th><th className="px-3 py-2 text-right">优先级</th><th className="px-3 py-2 text-right">目标价</th><th className="px-3 py-2 text-right">低预警</th><th className="px-3 py-2 text-right">高预警</th><th className="px-3 py-2 text-left">备注</th><th className="px-3 py-2 text-right">操作</th></tr>
              </thead>
              <tbody>
                {watchlist.length ? watchlist.map((item) => {
                  const editing = editingWatchlistId === item.id;
                  return (
                    <tr key={item.id} className="border-t align-top">
                      <td className="px-3 py-2 font-medium">{item.instrument?.symbol ?? item.instrument_id}<div className="text-xs font-normal text-muted-foreground">{item.instrument?.name}</div></td>
                      <td className="px-3 py-2">{editing ? <input className="w-28 rounded-md border bg-background px-2 py-1" value={watchlistDraft.status || ""} onChange={(e) => setWatchlistDraft({ ...watchlistDraft, status: e.target.value })} /> : item.status}</td>
                      <td className="px-3 py-2 text-right">{editing ? <input className="w-16 rounded-md border bg-background px-2 py-1 text-right" value={watchlistDraft.priority || ""} onChange={(e) => setWatchlistDraft({ ...watchlistDraft, priority: e.target.value })} /> : item.priority}</td>
                      <td className="px-3 py-2 text-right">{editing ? <input className="w-20 rounded-md border bg-background px-2 py-1 text-right" value={watchlistDraft.target_price || ""} onChange={(e) => setWatchlistDraft({ ...watchlistDraft, target_price: e.target.value })} /> : money(item.target_price)}</td>
                      <td className="px-3 py-2 text-right">{editing ? <input className="w-20 rounded-md border bg-background px-2 py-1 text-right" value={watchlistDraft.alert_price_low || ""} onChange={(e) => setWatchlistDraft({ ...watchlistDraft, alert_price_low: e.target.value })} /> : money(item.alert_price_low)}</td>
                      <td className="px-3 py-2 text-right">{editing ? <input className="w-20 rounded-md border bg-background px-2 py-1 text-right" value={watchlistDraft.alert_price_high || ""} onChange={(e) => setWatchlistDraft({ ...watchlistDraft, alert_price_high: e.target.value })} /> : money(item.alert_price_high)}</td>
                      <td className="max-w-[260px] px-3 py-2 text-muted-foreground">{editing ? <input className="w-full rounded-md border bg-background px-2 py-1" value={watchlistDraft.notes || ""} onChange={(e) => setWatchlistDraft({ ...watchlistDraft, notes: e.target.value })} /> : <span className="line-clamp-2">{item.notes || "-"}</span>}</td>
                      <td className="px-3 py-2">
                        <div className="flex justify-end gap-1">
                          {editing ? (
                            <>
                              <button onClick={() => saveWatchlist(item.id)} className="rounded-md border p-1.5 hover:bg-muted" title="保存"><Save className="h-4 w-4" /></button>
                              <button onClick={() => setEditingWatchlistId(null)} className="rounded-md border p-1.5 hover:bg-muted" title="取消"><X className="h-4 w-4" /></button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => startEditWatchlist(item)} className="rounded-md border p-1.5 hover:bg-muted" title="编辑"><Pencil className="h-4 w-4" /></button>
                              <button onClick={() => deleteWatchlist(item.id)} className="rounded-md border p-1.5 text-danger hover:bg-danger/10" title="删除"><Trash2 className="h-4 w-4" /></button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                }) : <EmptyRow colSpan={8} text={loading ? "加载中..." : "暂无关注项"} />}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <section className="rounded-md border bg-card">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <TriangleAlert className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">自动跟踪规则</h2>
            </div>
            <div className="grid gap-3 border-b p-4 md:grid-cols-6">
              <input className="rounded-md border bg-background px-3 py-2 text-sm md:col-span-2" placeholder="规则名称" value={ruleForm.name} onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })} />
              <select className="rounded-md border bg-background px-3 py-2 text-sm" value={ruleForm.instrument_id} onChange={(e) => setRuleForm({ ...ruleForm, instrument_id: e.target.value })}>
                <option value="">组合级</option>
                {instruments.map((item) => <option key={item.id} value={item.id}>{item.symbol}</option>)}
              </select>
              <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="类型" value={ruleForm.rule_type} onChange={(e) => setRuleForm({ ...ruleForm, rule_type: e.target.value })} />
              <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="频率" value={ruleForm.cadence} onChange={(e) => setRuleForm({ ...ruleForm, cadence: e.target.value })} />
              <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={ruleForm.is_enabled} onChange={(e) => setRuleForm({ ...ruleForm, is_enabled: e.target.checked })} />启用</label>
              <textarea className="min-h-20 rounded-md border bg-background px-3 py-2 font-mono text-xs md:col-span-3" value={ruleForm.condition} onChange={(e) => setRuleForm({ ...ruleForm, condition: e.target.value })} />
              <textarea className="min-h-20 rounded-md border bg-background px-3 py-2 font-mono text-xs md:col-span-3" value={ruleForm.action} onChange={(e) => setRuleForm({ ...ruleForm, action: e.target.value })} />
              <button onClick={createTrackingRule} disabled={saving || !ruleForm.name} className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                <Plus className="h-4 w-4" />
                新增规则
              </button>
            </div>
            <div className="overflow-auto">
              <table className="w-full min-w-[960px] text-sm">
                <thead className="bg-muted/50 text-xs text-muted-foreground">
                  <tr><th className="px-3 py-2 text-left">名称</th><th className="px-3 py-2 text-left">标的</th><th className="px-3 py-2 text-left">类型/频率</th><th className="px-3 py-2 text-left">条件</th><th className="px-3 py-2 text-left">动作</th><th className="px-3 py-2 text-left">状态</th><th className="px-3 py-2 text-right">操作</th></tr>
                </thead>
                <tbody>
                  {trackingRules.length ? trackingRules.map((item) => {
                    const editing = editingRuleId === item.id;
                    const instrument = instruments.find((inst) => inst.id === item.instrument_id);
                    return (
                      <tr key={item.id} className="border-t align-top">
                        <td className="px-3 py-2 font-medium">{editing ? <input className="w-40 rounded-md border bg-background px-2 py-1" value={ruleDraft.name || ""} onChange={(e) => setRuleDraft({ ...ruleDraft, name: e.target.value })} /> : item.name}</td>
                        <td className="px-3 py-2">{editing ? <select className="w-28 rounded-md border bg-background px-2 py-1" value={ruleDraft.instrument_id || ""} onChange={(e) => setRuleDraft({ ...ruleDraft, instrument_id: e.target.value })}><option value="">组合级</option>{instruments.map((inst) => <option key={inst.id} value={inst.id}>{inst.symbol}</option>)}</select> : instrument?.symbol || "组合级"}</td>
                        <td className="px-3 py-2">{editing ? <div className="grid gap-1"><input className="w-32 rounded-md border bg-background px-2 py-1" value={ruleDraft.rule_type || ""} onChange={(e) => setRuleDraft({ ...ruleDraft, rule_type: e.target.value })} /><input className="w-32 rounded-md border bg-background px-2 py-1" value={ruleDraft.cadence || ""} onChange={(e) => setRuleDraft({ ...ruleDraft, cadence: e.target.value })} /></div> : <>{item.rule_type}<div className="text-xs text-muted-foreground">{item.cadence || "-"}</div></>}</td>
                        <td className="max-w-[240px] px-3 py-2">{editing ? <textarea className="h-24 w-64 rounded-md border bg-background px-2 py-1 font-mono text-xs" value={ruleDraft.condition || "{}"} onChange={(e) => setRuleDraft({ ...ruleDraft, condition: e.target.value })} /> : <code className="line-clamp-3 text-xs text-muted-foreground">{compactJson(item.condition)}</code>}</td>
                        <td className="max-w-[220px] px-3 py-2">{editing ? <textarea className="h-24 w-56 rounded-md border bg-background px-2 py-1 font-mono text-xs" value={ruleDraft.action || "{}"} onChange={(e) => setRuleDraft({ ...ruleDraft, action: e.target.value })} /> : <code className="line-clamp-3 text-xs text-muted-foreground">{compactJson(item.action)}</code>}</td>
                        <td className="px-3 py-2">{editing ? <select className="rounded-md border bg-background px-2 py-1" value={ruleDraft.is_enabled || "true"} onChange={(e) => setRuleDraft({ ...ruleDraft, is_enabled: e.target.value })}><option value="true">启用</option><option value="false">停用</option></select> : item.is_enabled ? "启用" : "停用"}</td>
                        <td className="px-3 py-2">
                          <div className="flex justify-end gap-1">
                            {editing ? (
                              <>
                                <button onClick={() => saveTrackingRule(item.id)} className="rounded-md border p-1.5 hover:bg-muted" title="保存"><Save className="h-4 w-4" /></button>
                                <button onClick={() => setEditingRuleId(null)} className="rounded-md border p-1.5 hover:bg-muted" title="取消"><X className="h-4 w-4" /></button>
                              </>
                            ) : (
                              <>
                                <button onClick={() => startEditRule(item)} className="rounded-md border p-1.5 hover:bg-muted" title="编辑"><Pencil className="h-4 w-4" /></button>
                                <button onClick={() => deleteTrackingRule(item.id)} className="rounded-md border p-1.5 text-danger hover:bg-danger/10" title="删除"><Trash2 className="h-4 w-4" /></button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  }) : <EmptyRow colSpan={7} text={loading ? "加载中..." : "暂无规则"} />}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-md border bg-card">
            <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
              <div className="flex items-center gap-2">
                <ClipboardList className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-semibold">规则触发事件</h2>
              </div>
              <div className="text-xs text-muted-foreground">每页 10 条</div>
            </div>
            <div className="overflow-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="bg-muted/50 text-xs text-muted-foreground">
                  <tr><th className="px-3 py-2 text-left">时间</th><th className="px-3 py-2 text-left">规则</th><th className="px-3 py-2 text-left">标的</th><th className="px-3 py-2 text-left">原因</th><th className="px-3 py-2 text-left">状态</th></tr>
                </thead>
                <tbody>
                  {ruleEvents?.items.length ? ruleEvents.items.map((event) => (
                    <tr key={event.id} className="border-t align-top">
                      <td className="px-3 py-2 text-xs text-muted-foreground">{timeText(event.triggered_at)}</td>
                      <td className="px-3 py-2">{event.rule_name || event.rule_id}<div className="text-xs text-muted-foreground">{event.rule_type || "-"}</div></td>
                      <td className="px-3 py-2">{String(event.payload.symbol || event.payload.instrument_id || "组合级")}</td>
                      <td className="max-w-[260px] px-3 py-2 text-muted-foreground">{String(event.payload.reason || compactJson(event.payload))}</td>
                      <td className="px-3 py-2">{event.status}</td>
                    </tr>
                  )) : <EmptyRow colSpan={5} text={loading ? "加载中..." : "暂无触发事件"} />}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t px-4 py-3 text-sm">
              <span className="text-muted-foreground">共 {ruleEvents?.total ?? 0} 条</span>
              <div className="flex gap-2">
                <button className="rounded-md border px-3 py-1.5 disabled:opacity-50" disabled={ruleEventOffset <= 0} onClick={() => setRuleEventOffset(Math.max(0, ruleEventOffset - 10))}>上一页</button>
                <button className="rounded-md border px-3 py-1.5 disabled:opacity-50" disabled={(ruleEventOffset + 10) >= (ruleEvents?.total ?? 0)} onClick={() => setRuleEventOffset(ruleEventOffset + 10)}>下一页</button>
              </div>
            </div>
          </section>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-md border bg-card">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <FileText className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">最近研报</h2>
            </div>
            <div className="divide-y">
              {reports.length ? reports.map((report) => (
                <div key={report.id} className="p-4">
                  <div className="text-sm font-medium">{report.title}</div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{report.summary || report.content || "无摘要"}</p>
                </div>
              )) : <div className="p-8 text-center text-sm text-muted-foreground">暂无研报</div>}
            </div>
          </section>

          <section className="rounded-md border bg-card">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <ClipboardList className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">决策日志</h2>
            </div>
            <div className="grid gap-3 border-b p-4 md:grid-cols-4">
              <select className="rounded-md border bg-background px-3 py-2 text-sm" value={decisionForm.decision_type} onChange={(e) => setDecisionForm({ ...decisionForm, decision_type: e.target.value })}>
                <option value="watch">观察</option>
                <option value="buy">买入</option>
                <option value="sell">卖出</option>
                <option value="hold">持有</option>
                <option value="rebalance">调仓</option>
              </select>
              <select className="rounded-md border bg-background px-3 py-2 text-sm" value={decisionForm.instrument_id} onChange={(e) => setDecisionForm({ ...decisionForm, instrument_id: e.target.value })}>
                <option value="">组合级</option>
                {instruments.map((item) => <option key={item.id} value={item.id}>{item.symbol}</option>)}
              </select>
              <input className="rounded-md border bg-background px-3 py-2 text-sm md:col-span-2" placeholder="决策标题" value={decisionForm.title} onChange={(e) => setDecisionForm({ ...decisionForm, title: e.target.value })} />
              <textarea className="min-h-20 rounded-md border bg-background px-3 py-2 text-sm md:col-span-4" placeholder="决策依据" value={decisionForm.rationale} onChange={(e) => setDecisionForm({ ...decisionForm, rationale: e.target.value })} />
              <button onClick={createDecision} disabled={saving || !decisionForm.title || !decisionForm.rationale} className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                <Plus className="h-4 w-4" />
                记录决策
              </button>
            </div>
            <div className="divide-y">
              {decisions.length ? decisions.map((item) => (
                <div key={item.id} className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium">{item.title}</div>
                    <span className="rounded border px-2 py-0.5 text-xs text-muted-foreground">{item.decision_type}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{item.rationale}</p>
                </div>
              )) : <div className="p-8 text-center text-sm text-muted-foreground">暂无决策</div>}
            </div>
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-md border bg-card">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <Target className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">投资标的</h2>
            </div>
            <div className="grid gap-3 border-b p-4 md:grid-cols-6">
              <input className="rounded-md border bg-background px-3 py-2 text-sm md:col-span-1" placeholder="代码" value={instrumentForm.symbol} onChange={(e) => setInstrumentForm({ ...instrumentForm, symbol: e.target.value })} />
              <input className="rounded-md border bg-background px-3 py-2 text-sm md:col-span-2" placeholder="名称" value={instrumentForm.name} onChange={(e) => setInstrumentForm({ ...instrumentForm, name: e.target.value })} />
              <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="市场" value={instrumentForm.market} onChange={(e) => setInstrumentForm({ ...instrumentForm, market: e.target.value })} />
              <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="标签,逗号分隔" value={instrumentForm.tags} onChange={(e) => setInstrumentForm({ ...instrumentForm, tags: e.target.value })} />
              <button onClick={createInstrument} disabled={saving || !instrumentForm.symbol || !instrumentForm.name} className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                <Plus className="h-4 w-4" />
                新增
              </button>
              <textarea className="min-h-16 rounded-md border bg-background px-3 py-2 text-sm md:col-span-6" placeholder="跟踪理由 / 投资假设" value={instrumentForm.thesis} onChange={(e) => setInstrumentForm({ ...instrumentForm, thesis: e.target.value })} />
            </div>
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-xs text-muted-foreground">
                  <tr><th className="px-3 py-2 text-left">代码</th><th className="px-3 py-2 text-left">名称</th><th className="px-3 py-2 text-left">市场</th><th className="px-3 py-2 text-left">标签</th><th className="px-3 py-2 text-left">假设</th><th className="px-3 py-2 text-right">操作</th></tr>
                </thead>
                <tbody>
                  {instruments.length ? instruments.map((item) => {
                    const editing = editingInstrumentId === item.id;
                    const watchlisted = watchlistedInstrumentIds.has(item.id);
                    return (
                    <tr key={item.id} className="border-t align-top">
                      <td className="px-3 py-2 font-medium">{editing ? <input className="w-24 rounded-md border bg-background px-2 py-1" value={instrumentDraft.symbol || ""} onChange={(e) => setInstrumentDraft({ ...instrumentDraft, symbol: e.target.value })} /> : item.symbol}</td>
                      <td className="px-3 py-2">{editing ? <input className="w-32 rounded-md border bg-background px-2 py-1" value={instrumentDraft.name || ""} onChange={(e) => setInstrumentDraft({ ...instrumentDraft, name: e.target.value })} /> : item.name}</td>
                      <td className="px-3 py-2">{editing ? <input className="w-20 rounded-md border bg-background px-2 py-1" value={instrumentDraft.market || ""} onChange={(e) => setInstrumentDraft({ ...instrumentDraft, market: e.target.value })} /> : item.market}</td>
                      <td className="px-3 py-2">{editing ? <input className="w-36 rounded-md border bg-background px-2 py-1" value={instrumentDraft.tags || ""} onChange={(e) => setInstrumentDraft({ ...instrumentDraft, tags: e.target.value })} /> : (item.tags?.join(", ") || "-")}</td>
                      <td className="max-w-[320px] px-3 py-2 text-muted-foreground">{editing ? <input className="w-full rounded-md border bg-background px-2 py-1" value={instrumentDraft.thesis || ""} onChange={(e) => setInstrumentDraft({ ...instrumentDraft, thesis: e.target.value })} /> : <span className="line-clamp-2" title={item.thesis || undefined}>{item.thesis || "-"}</span>}</td>
                      <td className="px-3 py-2">
                        <div className="flex justify-end gap-1">
                          {editing ? (
                            <>
                              <button onClick={() => saveInstrument(item.id)} className="rounded-md border p-1.5 hover:bg-muted" title="保存"><Save className="h-4 w-4" /></button>
                              <button onClick={() => setEditingInstrumentId(null)} className="rounded-md border p-1.5 hover:bg-muted" title="取消"><X className="h-4 w-4" /></button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => addToWatchlist(item)} disabled={saving || watchlisted} className="rounded-md border p-1.5 hover:bg-muted disabled:cursor-not-allowed disabled:opacity-45" title={watchlisted ? "已关注" : "加关注"}><Eye className="h-4 w-4" /></button>
                              <button onClick={() => startEditInstrument(item)} className="rounded-md border p-1.5 hover:bg-muted" title="编辑"><Pencil className="h-4 w-4" /></button>
                              <button onClick={() => deleteInstrument(item.id)} className="rounded-md border p-1.5 text-danger hover:bg-danger/10" title="删除"><Trash2 className="h-4 w-4" /></button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}) : <EmptyRow colSpan={6} text={loading ? "加载中..." : "暂无标的"} />}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-md border bg-card">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <LineChart className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">持仓录入</h2>
            </div>
            <div className="space-y-3 p-4">
              <select className="w-full rounded-md border bg-background px-3 py-2 text-sm" value={positionForm.instrument_id} onChange={(e) => setPositionForm({ ...positionForm, instrument_id: e.target.value })}>
                <option value="">选择标的</option>
                {instruments.map((item) => <option key={item.id} value={item.id}>{item.symbol} · {item.name}</option>)}
              </select>
              <div className="grid grid-cols-3 gap-3">
                <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="数量" value={positionForm.quantity} onChange={(e) => setPositionForm({ ...positionForm, quantity: e.target.value })} />
                <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="均价" value={positionForm.avg_cost} onChange={(e) => setPositionForm({ ...positionForm, avg_cost: e.target.value })} />
                <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="目标权重 %" title="输入百分比，例如 20 表示 20%" value={positionForm.target_weight} onChange={(e) => setPositionForm({ ...positionForm, target_weight: e.target.value })} />
              </div>
              <textarea className="min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm" placeholder={selectedInstrument ? `${selectedInstrument.symbol} 持仓备注` : "持仓备注"} value={positionForm.notes} onChange={(e) => setPositionForm({ ...positionForm, notes: e.target.value })} />
              <button onClick={createPosition} disabled={saving || !positionForm.instrument_id || !positionForm.quantity || !positionForm.avg_cost} className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                <Plus className="h-4 w-4" />
                保存持仓
              </button>
            </div>
          </section>
        </div>

        <section className="rounded-md border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <ImageUp className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">持仓截图导入</h2>
            </div>
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted">
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImageUp className="h-4 w-4" />}
              上传截图
              <input type="file" accept="image/*" className="hidden" onChange={(e) => uploadScreenshot(e.target.files?.[0] ?? null)} disabled={uploading} />
            </label>
          </div>

          <div className="grid gap-0 lg:grid-cols-[260px_1fr]">
            <div className="border-b lg:border-b-0 lg:border-r">
              {importJobs.length ? importJobs.map((job) => (
                <button
                  key={job.id}
                  onClick={() => setActiveImport(job)}
                  className={cn(
                    "block w-full border-b px-4 py-3 text-left text-sm hover:bg-muted/60",
                    activeImport?.id === job.id && "bg-primary/10 text-primary",
                  )}
                >
                  <div className="truncate font-medium">{job.filename}</div>
                  <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                    <span>{job.status}</span>
                    <span>{job.items.length} 行</span>
                  </div>
                </button>
              )) : (
                <div className="p-6 text-center text-sm text-muted-foreground">暂无导入任务</div>
              )}
            </div>

            <div className="min-w-0">
              {activeImport ? (
                <>
                  <div className="grid gap-3 border-b p-4 md:grid-cols-4">
                    <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="券商" value={activeImport.broker ?? ""} onChange={(e) => setActiveImport({ ...activeImport, broker: e.target.value })} />
                    <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="账户名称" value={activeImport.account_name ?? ""} onChange={(e) => setActiveImport({ ...activeImport, account_name: e.target.value })} />
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      {activeImport.status === "ready_to_save" || activeImport.status === "saved" ? <CheckCircle2 className="h-4 w-4 text-success" /> : <TriangleAlert className="h-4 w-4 text-warning" />}
                      {activeImport.status}
                    </div>
                    <div className="flex gap-2">
                      <button onClick={addManualImportItem} disabled={saving} className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50">
                        <Plus className="h-4 w-4" />
                        加行
                      </button>
                      <button onClick={saveImportReview} disabled={saving} className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm hover:bg-muted disabled:opacity-50">
                        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                        检查
                      </button>
                      <button onClick={confirmImport} disabled={saving || activeImport.status !== "ready_to_save"} className="inline-flex flex-1 items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50">
                        保存
                      </button>
                    </div>
                    {activeImport.summary ? <div className="text-sm text-muted-foreground md:col-span-4">{activeImport.summary}</div> : null}
                    {activeImport.warnings.length ? (
                      <div className="rounded-md border border-warning/30 bg-warning/10 p-3 text-sm text-warning md:col-span-4">
                        {activeImport.warnings.join("；")}
                      </div>
                    ) : null}
                  </div>

                  <div className="overflow-auto">
                    <table className="w-full min-w-[980px] text-sm">
                      <thead className="bg-muted/50 text-xs text-muted-foreground">
                        <tr>
                          <th className="px-3 py-2 text-left">状态</th><th className="px-3 py-2 text-left">代码</th><th className="px-3 py-2 text-left">名称</th><th className="px-3 py-2 text-left">市场</th><th className="px-3 py-2 text-left">币种</th><th className="px-3 py-2 text-right">数量</th><th className="px-3 py-2 text-right">成本价</th><th className="px-3 py-2 text-right">现价</th><th className="px-3 py-2 text-left">缺失/提醒</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeImport.items.length ? activeImport.items.map((item, idx) => (
                          <tr key={item.id} className="border-t align-top">
                            <td className="px-3 py-2">
                              <select className="w-28 rounded-md border bg-background px-2 py-1 text-xs" value={item.status} onChange={(e) => updateImportItem(idx, { status: e.target.value })}>
                                <option value="needs_review">待核实</option>
                                <option value="ready">可保存</option>
                                <option value="skipped">跳过</option>
                              </select>
                            </td>
                            <td className="px-3 py-2"><input className="w-24 rounded-md border bg-background px-2 py-1" value={item.symbol ?? ""} onChange={(e) => updateImportItem(idx, { symbol: e.target.value })} /></td>
                            <td className="px-3 py-2"><input className="w-36 rounded-md border bg-background px-2 py-1" value={item.name ?? ""} onChange={(e) => updateImportItem(idx, { name: e.target.value })} /></td>
                            <td className="px-3 py-2"><input className="w-20 rounded-md border bg-background px-2 py-1" value={item.market ?? ""} onChange={(e) => updateImportItem(idx, { market: e.target.value })} /></td>
                            <td className="px-3 py-2"><input className="w-20 rounded-md border bg-background px-2 py-1" value={item.currency ?? ""} onChange={(e) => updateImportItem(idx, { currency: e.target.value })} /></td>
                            <td className="px-3 py-2"><input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={item.quantity ?? ""} onChange={(e) => updateImportItem(idx, { quantity: optionalNumberInput(e.target.value) })} /></td>
                            <td className="px-3 py-2"><input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={item.avg_cost ?? ""} onChange={(e) => updateImportItem(idx, { avg_cost: optionalNumberInput(e.target.value) })} /></td>
                            <td className="px-3 py-2"><input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={item.market_price ?? ""} onChange={(e) => updateImportItem(idx, { market_price: optionalNumberInput(e.target.value) })} /></td>
                            <td className="max-w-[260px] px-3 py-2 text-xs text-muted-foreground">
                              {[...item.missing_fields.map((field) => `缺 ${field}`), ...item.warnings].join("；") || `置信度 ${pctFmt.format(item.confidence || 0)}`}
                            </td>
                          </tr>
                        )) : <EmptyRow colSpan={9} text="未识别到明细，请人工补录或换一张更清晰的截图" />}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <div className="p-10 text-center text-sm text-muted-foreground">上传券商持仓截图后，会在这里显示可编辑的识别结果和完整性检查。</div>
              )}
            </div>
          </div>
        </section>

        {watchlist.length ? (
          <div className="text-xs text-muted-foreground">
            已关注 {watchlist.length} 个标的，后续自动研究任务会优先读取这些标的和持仓数据。
          </div>
        ) : null}
      </div>
    </div>
  );
}
