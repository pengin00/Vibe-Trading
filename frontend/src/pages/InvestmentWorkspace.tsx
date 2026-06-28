import { useEffect, useMemo, useState } from "react";
import { BriefcaseBusiness, CheckCircle2, ClipboardList, FileText, ImageUp, LineChart, Loader2, Plus, RefreshCw, Target, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type PortfolioDashboard, type PortfolioDecision, type PortfolioInstrument, type PortfolioPosition, type PortfolioResearchReport, type PortfolioWatchlistItem, type PositionImportItemPatch, type PositionImportJob } from "@/lib/api";
import { cn } from "@/lib/utils";

const numberFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const pctFmt = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 2 });

function money(value: number | null | undefined) {
  return numberFmt.format(value ?? 0);
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
  const [importJobs, setImportJobs] = useState<PositionImportJob[]>([]);
  const [activeImport, setActiveImport] = useState<PositionImportJob | null>(null);
  const [uploading, setUploading] = useState(false);
  const [instrumentForm, setInstrumentForm] = useState({ symbol: "", name: "", market: "US", asset_class: "equity", currency: "USD", tags: "", thesis: "" });
  const [positionForm, setPositionForm] = useState({ instrument_id: "", quantity: "", avg_cost: "", target_weight: "", notes: "" });
  const [decisionForm, setDecisionForm] = useState({ instrument_id: "", decision_type: "watch", title: "", rationale: "" });

  const selectedInstrument = useMemo(
    () => instruments.find((item) => item.id === positionForm.instrument_id),
    [instruments, positionForm.instrument_id],
  );

  const load = async () => {
    setError(null);
    setLoading(true);
    try {
      const [dash, inst, watch, pos, reps, decs, jobs] = await Promise.all([
        api.portfolio.dashboard(),
        api.portfolio.listInstruments(),
        api.portfolio.listWatchlist(),
        api.portfolio.listPositions(),
        api.portfolio.listResearchReports(),
        api.portfolio.listDecisions(),
        api.portfolio.listImports(),
      ]);
      setDashboard(dash);
      setInstruments(inst);
      setWatchlist(watch);
      setPositions(pos);
      setReports(reps);
      setDecisions(decs);
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
        target_weight: positionForm.target_weight ? Number(positionForm.target_weight) : null,
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

        <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-md border bg-card">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <Target className="h-4 w-4 text-primary" />
              <h2 className="text-sm font-semibold">投资标的与关注列表</h2>
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
                  <tr><th className="px-3 py-2 text-left">代码</th><th className="px-3 py-2 text-left">名称</th><th className="px-3 py-2 text-left">市场</th><th className="px-3 py-2 text-left">标签</th><th className="px-3 py-2 text-left">假设</th></tr>
                </thead>
                <tbody>
                  {instruments.length ? instruments.map((item) => (
                    <tr key={item.id} className="border-t">
                      <td className="px-3 py-2 font-medium">{item.symbol}</td>
                      <td className="px-3 py-2">{item.name}</td>
                      <td className="px-3 py-2">{item.market}</td>
                      <td className="px-3 py-2">{item.tags?.join(", ") || "-"}</td>
                      <td className="max-w-[320px] truncate px-3 py-2 text-muted-foreground">{item.thesis || "-"}</td>
                    </tr>
                  )) : <EmptyRow colSpan={5} text={loading ? "加载中..." : "暂无标的"} />}
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
                <input className="rounded-md border bg-background px-3 py-2 text-sm" placeholder="目标权重" value={positionForm.target_weight} onChange={(e) => setPositionForm({ ...positionForm, target_weight: e.target.value })} />
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
                            <td className="px-3 py-2"><input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={item.quantity ?? ""} onChange={(e) => updateImportItem(idx, { quantity: Number(e.target.value) || null })} /></td>
                            <td className="px-3 py-2"><input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={item.avg_cost ?? ""} onChange={(e) => updateImportItem(idx, { avg_cost: Number(e.target.value) || null })} /></td>
                            <td className="px-3 py-2"><input className="w-24 rounded-md border bg-background px-2 py-1 text-right" value={item.market_price ?? ""} onChange={(e) => updateImportItem(idx, { market_price: Number(e.target.value) || null })} /></td>
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

        <section className="rounded-md border bg-card">
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <ClipboardList className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">当前持仓</h2>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr><th className="px-3 py-2 text-left">标的</th><th className="px-3 py-2 text-right">数量</th><th className="px-3 py-2 text-right">均价</th><th className="px-3 py-2 text-right">成本</th><th className="px-3 py-2 text-right">市值</th><th className="px-3 py-2 text-right">盈亏</th><th className="px-3 py-2 text-left">备注</th></tr>
              </thead>
              <tbody>
                {positions.length ? positions.map((item) => (
                  <tr key={item.id} className="border-t">
                    <td className="px-3 py-2 font-medium">{item.instrument?.symbol ?? item.instrument_id}</td>
                    <td className="px-3 py-2 text-right">{money(item.quantity)}</td>
                    <td className="px-3 py-2 text-right">{money(item.avg_cost)}</td>
                    <td className="px-3 py-2 text-right">{money(item.cost_basis)}</td>
                    <td className="px-3 py-2 text-right">{money(item.market_value)}</td>
                    <td className={cn("px-3 py-2 text-right", item.unrealized_pnl >= 0 ? "text-success" : "text-danger")}>{money(item.unrealized_pnl)} · {pctFmt.format(item.unrealized_pnl_pct || 0)}</td>
                    <td className="max-w-[280px] truncate px-3 py-2 text-muted-foreground">{item.notes || "-"}</td>
                  </tr>
                )) : <EmptyRow colSpan={7} text={loading ? "加载中..." : "暂无持仓"} />}
              </tbody>
            </table>
          </div>
        </section>

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

        {watchlist.length ? (
          <div className="text-xs text-muted-foreground">
            已关注 {watchlist.length} 个标的，后续自动研究任务会优先读取这些标的和持仓数据。
          </div>
        ) : null}
      </div>
    </div>
  );
}
