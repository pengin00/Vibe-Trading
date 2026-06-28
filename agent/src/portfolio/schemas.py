"""API schemas for the investment workspace.

这里的 schema 字段说明使用中文，FastAPI 生成 OpenAPI 时会直接展示这些说明。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PortfolioBaseModel(BaseModel):
    model_config = {"from_attributes": True}


class PortfolioAccountCreate(PortfolioBaseModel):
    name: str = Field(..., description="账户名称")
    broker: str | None = Field(None, description="券商或账户来源")
    account_type: str = Field("manual", description="账户类型：manual/paper/live等")
    base_currency: str = Field("USD", description="账户基础币种")
    cash_balance: float = Field(0.0, description="现金余额")
    notes: str | None = Field(None, description="账户备注")


class PortfolioAccountUpdate(PortfolioBaseModel):
    name: str | None = Field(None, description="账户名称")
    broker: str | None = Field(None, description="券商或账户来源")
    account_type: str | None = Field(None, description="账户类型")
    base_currency: str | None = Field(None, description="账户基础币种")
    cash_balance: float | None = Field(None, description="现金余额")
    notes: str | None = Field(None, description="账户备注")
    is_active: bool | None = Field(None, description="是否启用")


class PortfolioAccountOut(PortfolioAccountCreate):
    id: str = Field(..., description="账户ID")
    is_active: bool = Field(..., description="是否启用")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class InstrumentCreate(PortfolioBaseModel):
    symbol: str = Field(..., description="交易代码，例如 AAPL、GOOGL、510300")
    name: str = Field(..., description="标的名称")
    market: str = Field("US", description="市场代码，例如 US、HK、CN、CRYPTO")
    asset_class: str = Field("equity", description="资产类别：equity/etf/fund/bond/crypto/cash等")
    currency: str = Field("USD", description="计价币种")
    sector: str | None = Field(None, description="行业或板块")
    region: str | None = Field(None, description="地区")
    tags: list[str] = Field(default_factory=list, description="自定义标签列表")
    thesis: str | None = Field(None, description="长期跟踪理由或投资假设")
    data_source: str | None = Field(None, description="首选行情/基本面数据源")


class InstrumentUpdate(PortfolioBaseModel):
    symbol: str | None = Field(None, description="交易代码")
    name: str | None = Field(None, description="标的名称")
    market: str | None = Field(None, description="市场代码")
    asset_class: str | None = Field(None, description="资产类别")
    currency: str | None = Field(None, description="计价币种")
    sector: str | None = Field(None, description="行业或板块")
    region: str | None = Field(None, description="地区")
    tags: list[str] | None = Field(None, description="自定义标签列表")
    thesis: str | None = Field(None, description="长期跟踪理由或投资假设")
    data_source: str | None = Field(None, description="首选数据源")
    is_active: bool | None = Field(None, description="是否持续跟踪")


class InstrumentOut(InstrumentCreate):
    id: str = Field(..., description="标的ID")
    is_active: bool = Field(..., description="是否持续跟踪")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class WatchlistItemCreate(PortfolioBaseModel):
    instrument_id: str = Field(..., description="关联标的ID")
    priority: int = Field(3, ge=1, le=5, description="跟踪优先级：1最高，5最低")
    status: str = Field("watching", description="跟踪状态")
    target_price: float | None = Field(None, description="目标价")
    alert_price_low: float | None = Field(None, description="低价提醒阈值")
    alert_price_high: float | None = Field(None, description="高价提醒阈值")
    notes: str | None = Field(None, description="关注备注")


class WatchlistItemUpdate(PortfolioBaseModel):
    priority: int | None = Field(None, ge=1, le=5, description="跟踪优先级")
    status: str | None = Field(None, description="跟踪状态")
    target_price: float | None = Field(None, description="目标价")
    alert_price_low: float | None = Field(None, description="低价提醒阈值")
    alert_price_high: float | None = Field(None, description="高价提醒阈值")
    notes: str | None = Field(None, description="关注备注")


class WatchlistItemOut(WatchlistItemCreate):
    id: str = Field(..., description="关注条目ID")
    instrument: InstrumentOut | None = Field(None, description="关联标的信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class PositionCreate(PortfolioBaseModel):
    account_id: str | None = Field(None, description="账户ID；为空时使用默认手工账户")
    instrument_id: str = Field(..., description="标的ID")
    quantity: float = Field(0.0, description="当前持仓数量")
    avg_cost: float = Field(0.0, description="平均成本")
    cost_basis: float | None = Field(None, description="总成本；为空时按数量乘均价计算")
    target_weight: float | None = Field(None, ge=0, le=1, description="目标仓位权重，0到1")
    stop_loss: float | None = Field(None, description="止损价")
    take_profit: float | None = Field(None, description="止盈价")
    notes: str | None = Field(None, description="持仓备注")


class PositionUpdate(PortfolioBaseModel):
    quantity: float | None = Field(None, description="当前持仓数量")
    avg_cost: float | None = Field(None, description="平均成本")
    cost_basis: float | None = Field(None, description="总成本")
    target_weight: float | None = Field(None, ge=0, le=1, description="目标仓位权重")
    stop_loss: float | None = Field(None, description="止损价")
    take_profit: float | None = Field(None, description="止盈价")
    notes: str | None = Field(None, description="持仓备注")


class PositionOut(PositionCreate):
    id: str = Field(..., description="持仓ID")
    account_id: str = Field(..., description="账户ID")
    instrument: InstrumentOut | None = Field(None, description="关联标的信息")
    account: PortfolioAccountOut | None = Field(None, description="关联账户信息")
    market_price: float | None = Field(None, description="最新估值价格")
    market_price_as_of: datetime | None = Field(None, description="最新估值价格时间")
    market_price_source: str | None = Field(None, description="最新估值价格来源")
    market_value: float = Field(0.0, description="最新市值")
    unrealized_pnl: float = Field(0.0, description="未实现盈亏")
    unrealized_pnl_pct: float = Field(0.0, description="未实现盈亏比例")
    actual_weight: float | None = Field(None, description="实际仓位权重，0到1")
    weight_drift: float | None = Field(None, description="实际权重减目标权重，0到1")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class PositionLotCreate(PortfolioBaseModel):
    position_id: str = Field(..., description="持仓ID")
    side: Literal["buy", "sell", "transfer_in", "transfer_out", "adjustment"] = Field(..., description="交易方向")
    quantity: float = Field(..., gt=0, description="交易数量")
    price: float = Field(..., ge=0, description="成交价格")
    fees: float = Field(0.0, ge=0, description="交易费用")
    currency: str = Field("USD", description="交易币种")
    trade_date: datetime | None = Field(None, description="交易时间")
    notes: str | None = Field(None, description="流水备注")


class PositionLotOut(PositionLotCreate):
    id: str = Field(..., description="流水ID")
    trade_date: datetime = Field(..., description="交易时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class PriceSnapshotCreate(PortfolioBaseModel):
    instrument_id: str = Field(..., description="标的ID")
    as_of: datetime | None = Field(None, description="价格时间")
    price: float = Field(..., description="最新价格")
    change_pct: float | None = Field(None, description="涨跌幅")
    source: str | None = Field(None, description="数据来源")
    raw: dict[str, Any] = Field(default_factory=dict, description="原始行情数据")


class PriceSnapshotOut(PriceSnapshotCreate):
    id: str = Field(..., description="价格快照ID")
    as_of: datetime = Field(..., description="价格时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class ResearchReportCreate(PortfolioBaseModel):
    instrument_id: str | None = Field(None, description="关联标的ID；为空表示组合级报告")
    title: str = Field(..., description="报告标题")
    report_type: str = Field("research", description="报告类型")
    summary: str | None = Field(None, description="摘要")
    content_path: str | None = Field(None, description="报告文件路径")
    content: str | None = Field(None, description="报告正文")
    rating: str | None = Field(None, description="评级或建议")
    confidence: float | None = Field(None, ge=0, le=1, description="置信度，0到1")
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="证据列表")
    generated_by: str | None = Field(None, description="生成来源：agent/user/system")


class ResearchReportOut(ResearchReportCreate):
    id: str = Field(..., description="研报ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class TrackingRuleCreate(PortfolioBaseModel):
    instrument_id: str | None = Field(None, description="关联标的ID；为空表示组合级规则")
    name: str = Field(..., description="规则名称")
    rule_type: str = Field(..., description="规则类型：price/news/earnings/risk/rebalance等")
    condition: dict[str, Any] = Field(default_factory=dict, description="触发条件JSON")
    action: dict[str, Any] = Field(default_factory=dict, description="触发后的动作JSON")
    cadence: str | None = Field(None, description="检查频率")
    next_run_date: datetime | None = Field(None, description="下次执行时间")
    is_enabled: bool = Field(True, description="是否启用")


class TrackingRuleUpdate(PortfolioBaseModel):
    name: str | None = Field(None, description="规则名称")
    rule_type: str | None = Field(None, description="规则类型")
    condition: dict[str, Any] | None = Field(None, description="触发条件JSON")
    action: dict[str, Any] | None = Field(None, description="触发后的动作JSON")
    cadence: str | None = Field(None, description="检查频率")
    next_run_date: datetime | None = Field(None, description="下次执行时间")
    is_enabled: bool | None = Field(None, description="是否启用")


class TrackingRuleOut(TrackingRuleCreate):
    id: str = Field(..., description="规则ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class RuleTriggerEventOut(PortfolioBaseModel):
    id: str = Field(..., description="事件ID")
    rule_id: str = Field(..., description="规则ID")
    rule_name: str | None = Field(None, description="规则名称")
    rule_type: str | None = Field(None, description="规则类型")
    triggered_at: datetime = Field(..., description="触发时间")
    status: str = Field(..., description="事件状态")
    payload: dict[str, Any] = Field(default_factory=dict, description="触发上下文")
    result: dict[str, Any] = Field(default_factory=dict, description="执行结果")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class RuleTriggerEventPage(PortfolioBaseModel):
    total: int = Field(..., description="事件总数")
    limit: int = Field(..., description="每页数量")
    offset: int = Field(..., description="分页偏移")
    items: list[RuleTriggerEventOut] = Field(default_factory=list, description="事件列表")


class DecisionLogCreate(PortfolioBaseModel):
    instrument_id: str | None = Field(None, description="关联标的ID")
    decision_type: str = Field(..., description="决策类型：buy/sell/hold/watch/rebalance等")
    title: str = Field(..., description="决策标题")
    rationale: str = Field(..., description="决策依据")
    expected_outcome: str | None = Field(None, description="预期结果")
    review_date: datetime | None = Field(None, description="复盘时间")
    linked_report_id: str | None = Field(None, description="关联研报ID")


class DecisionLogOut(DecisionLogCreate):
    id: str = Field(..., description="决策ID")
    decision_date: datetime = Field(..., description="决策时间")
    status: str = Field(..., description="状态：open/reviewed/closed")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class PortfolioDashboard(PortfolioBaseModel):
    accounts: int = Field(..., description="账户数量")
    instruments: int = Field(..., description="标的数量")
    watchlist_items: int = Field(..., description="关注条目数量")
    positions: int = Field(..., description="持仓数量")
    total_cost_basis: float = Field(..., description="总成本")
    total_market_value: float = Field(..., description="总市值")
    total_unrealized_pnl: float = Field(..., description="总未实现盈亏")
    recent_reports: list[ResearchReportOut] = Field(default_factory=list, description="最近研报")


class PortfolioAutopilotRunRequest(PortfolioBaseModel):
    max_targets: int = Field(10, ge=1, le=100, description="本次自动研究最多处理的标的数量")
    create_reports: bool = Field(True, description="是否写入自动研究简报")
    refresh_prices: bool = Field(True, description="是否尝试刷新价格；关闭时只使用已有价格快照")


class PortfolioAutopilotScheduleRequest(PortfolioBaseModel):
    interval_seconds: int = Field(3600, ge=60, description="自动研究执行间隔，秒")
    max_targets: int = Field(10, ge=1, le=100, description="每次最多处理的标的数量")
    run_immediately: bool = Field(False, description="启动后是否立即执行一次")


class PortfolioAutopilotRunResponse(PortfolioBaseModel):
    status: str = Field(..., description="执行状态")
    started_at: datetime = Field(..., description="开始时间")
    finished_at: datetime = Field(..., description="结束时间")
    targets: list[dict[str, Any]] = Field(default_factory=list, description="本次处理的标的")
    price_snapshots: list[str] = Field(default_factory=list, description="新增价格快照ID")
    triggered_events: list[str] = Field(default_factory=list, description="触发事件ID")
    research_reports: list[str] = Field(default_factory=list, description="新增研报ID")
    errors: list[str] = Field(default_factory=list, description="错误列表")


class PositionImportItemPatch(PortfolioBaseModel):
    symbol: str | None = Field(None, description="交易代码")
    name: str | None = Field(None, description="标的名称")
    market: str | None = Field(None, description="市场代码")
    asset_class: str | None = Field(None, description="资产类别")
    currency: str | None = Field(None, description="币种")
    quantity: float | None = Field(None, description="持仓数量")
    available_quantity: float | None = Field(None, description="可用数量")
    avg_cost: float | None = Field(None, description="成本价")
    cost_basis: float | None = Field(None, description="持仓成本")
    market_price: float | None = Field(None, description="当前价")
    market_value: float | None = Field(None, description="市值")
    unrealized_pnl: float | None = Field(None, description="浮动盈亏")
    unrealized_pnl_pct: float | None = Field(None, description="浮动盈亏比例")
    status: str | None = Field(None, description="明细状态：needs_review/ready/saved/skipped")
    source_text: str | None = Field(None, description="识别来源文本")


class PositionImportItemOut(PositionImportItemPatch):
    id: str = Field(..., description="导入明细ID")
    job_id: str = Field(..., description="导入任务ID")
    row_index: int = Field(..., description="截图中的行序号")
    confidence: float = Field(..., description="整行识别置信度，0到1")
    field_confidence: dict[str, Any] = Field(default_factory=dict, description="字段级置信度")
    missing_fields: list[str] = Field(default_factory=list, description="该行缺失的必填字段")
    warnings: list[str] = Field(default_factory=list, description="该行校验警告")
    status: str = Field(..., description="明细状态：needs_review/ready/saved/skipped")
    saved_position_id: str | None = Field(None, description="保存后的持仓ID")
    raw: dict[str, Any] = Field(default_factory=dict, description="该行原始解析结果")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class PositionImportJobOut(PortfolioBaseModel):
    id: str = Field(..., description="导入任务ID")
    filename: str = Field(..., description="原始文件名")
    file_path: str = Field(..., description="截图文件保存路径")
    content_type: str | None = Field(None, description="上传文件MIME类型")
    broker: str | None = Field(None, description="券商或截图来源")
    account_name: str | None = Field(None, description="账户名称")
    status: str = Field(..., description="任务状态")
    parser: str = Field(..., description="解析方式")
    summary: str | None = Field(None, description="解析摘要或人工说明")
    raw_result: dict[str, Any] = Field(default_factory=dict, description="模型或OCR返回的原始结构化结果")
    missing_fields: list[str] = Field(default_factory=list, description="任务级缺失字段列表")
    warnings: list[str] = Field(default_factory=list, description="任务级校验警告")
    saved_at: datetime | None = Field(None, description="确认保存时间")
    items: list[PositionImportItemOut] = Field(default_factory=list, description="导入明细")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")


class PositionImportJobPatch(PortfolioBaseModel):
    broker: str | None = Field(None, description="券商或截图来源")
    account_name: str | None = Field(None, description="账户名称")
    summary: str | None = Field(None, description="人工说明")
    items: list[PositionImportItemPatch] | None = Field(None, description="人工修正后的导入明细")


class PositionImportConfirmRequest(PortfolioBaseModel):
    account_name: str | None = Field(None, description="保存到的账户名称；为空时使用任务账户或默认账户")
    broker: str | None = Field(None, description="券商或账户来源")
    overwrite_existing: bool = Field(True, description="如果已有同账户同标的持仓，是否覆盖数量和成本")
    save_price_snapshots: bool = Field(True, description="是否把截图里的当前价保存为价格快照")


class PositionImportConfirmResponse(PortfolioBaseModel):
    status: str = Field(..., description="保存状态")
    job_id: str = Field(..., description="导入任务ID")
    saved_positions: list[str] = Field(default_factory=list, description="保存或更新的持仓ID列表")
    skipped_items: list[str] = Field(default_factory=list, description="跳过的导入明细ID列表")
