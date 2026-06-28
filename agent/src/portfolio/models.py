"""SQLAlchemy schema for the investment workspace.

所有表和字段都带中文注释，PostgreSQL 建表时会写入 comment metadata，方便后续迁移、
审计和数据库可视化工具理解字段含义。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
        comment="最后更新时间",
    )


class PortfolioAccount(Base, TimestampMixin):
    """投资账户。"""

    __tablename__ = "portfolio_accounts"
    __table_args__ = {"comment": "投资账户表：记录券商账户、模拟账户或手工账户"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="账户ID")
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="账户名称")
    broker: Mapped[str | None] = mapped_column(String(80), comment="券商或账户来源")
    account_type: Mapped[str] = mapped_column(String(40), default="manual", nullable=False, comment="账户类型：manual/paper/live等")
    base_currency: Mapped[str] = mapped_column(String(12), default="USD", nullable=False, comment="账户基础币种")
    cash_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, comment="现金余额")
    notes: Mapped[str | None] = mapped_column(Text, comment="账户备注")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")


class Instrument(Base, TimestampMixin):
    """投资标的。"""

    __tablename__ = "portfolio_instruments"
    __table_args__ = (
        UniqueConstraint("symbol", "market", name="uq_portfolio_instrument_symbol_market"),
        {"comment": "投资标的表：记录股票、ETF、基金、债券、加密货币等可跟踪资产"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="标的ID")
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="交易代码，例如 AAPL、GOOGL、510300")
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="标的名称")
    market: Mapped[str] = mapped_column(String(40), default="US", nullable=False, comment="市场代码，例如 US、HK、CN、CRYPTO")
    asset_class: Mapped[str] = mapped_column(String(40), default="equity", nullable=False, comment="资产类别：equity/etf/fund/bond/crypto/cash等")
    currency: Mapped[str] = mapped_column(String(12), default="USD", nullable=False, comment="计价币种")
    sector: Mapped[str | None] = mapped_column(String(120), comment="行业或板块")
    region: Mapped[str | None] = mapped_column(String(80), comment="地区")
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False, comment="自定义标签列表")
    thesis: Mapped[str | None] = mapped_column(Text, comment="长期跟踪理由或投资假设")
    data_source: Mapped[str | None] = mapped_column(String(80), comment="首选行情/基本面数据源")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否持续跟踪")


class WatchlistItem(Base, TimestampMixin):
    """关注列表条目。"""

    __tablename__ = "portfolio_watchlist_items"
    __table_args__ = (
        UniqueConstraint("instrument_id", name="uq_portfolio_watchlist_instrument"),
        {"comment": "关注列表表：管理需要持续观察但未必持仓的投资标的"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="关注条目ID")
    instrument_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolio_instruments.id"), nullable=False, comment="关联标的ID")
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False, comment="跟踪优先级：1最高，5最低")
    status: Mapped[str] = mapped_column(String(40), default="watching", nullable=False, comment="跟踪状态：watching/researching/paused/closed")
    target_price: Mapped[float | None] = mapped_column(Float, comment="目标价")
    alert_price_low: Mapped[float | None] = mapped_column(Float, comment="低价提醒阈值")
    alert_price_high: Mapped[float | None] = mapped_column(Float, comment="高价提醒阈值")
    notes: Mapped[str | None] = mapped_column(Text, comment="关注备注")
    instrument: Mapped[Instrument] = relationship()


class Position(Base, TimestampMixin):
    """当前持仓。"""

    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("account_id", "instrument_id", name="uq_portfolio_position_account_instrument"),
        Index("ix_portfolio_positions_instrument", "instrument_id"),
        {"comment": "持仓表：记录账户维度的当前持仓汇总"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="持仓ID")
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolio_accounts.id"), nullable=False, comment="账户ID")
    instrument_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolio_instruments.id"), nullable=False, comment="标的ID")
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, comment="当前持仓数量")
    avg_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, comment="平均成本")
    cost_basis: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, comment="总成本")
    target_weight: Mapped[float | None] = mapped_column(Float, comment="目标仓位权重，0到1")
    stop_loss: Mapped[float | None] = mapped_column(Float, comment="止损价")
    take_profit: Mapped[float | None] = mapped_column(Float, comment="止盈价")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, comment="首次建仓时间")
    notes: Mapped[str | None] = mapped_column(Text, comment="持仓备注")
    account: Mapped[PortfolioAccount] = relationship()
    instrument: Mapped[Instrument] = relationship()


class PositionLot(Base, TimestampMixin):
    """持仓流水。"""

    __tablename__ = "portfolio_position_lots"
    __table_args__ = {"comment": "持仓流水表：记录买入、卖出、转入、转出和手工调整"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="流水ID")
    position_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolio_positions.id"), nullable=False, comment="持仓ID")
    trade_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, comment="交易时间")
    side: Mapped[str] = mapped_column(String(24), nullable=False, comment="交易方向：buy/sell/transfer_in/transfer_out/adjustment")
    quantity: Mapped[float] = mapped_column(Float, nullable=False, comment="交易数量")
    price: Mapped[float] = mapped_column(Float, nullable=False, comment="成交价格")
    fees: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, comment="交易费用")
    currency: Mapped[str] = mapped_column(String(12), default="USD", nullable=False, comment="交易币种")
    notes: Mapped[str | None] = mapped_column(Text, comment="流水备注")
    position: Mapped[Position] = relationship()


class PriceSnapshot(Base, TimestampMixin):
    """价格快照。"""

    __tablename__ = "portfolio_price_snapshots"
    __table_args__ = (
        Index("ix_portfolio_price_snapshots_instrument_asof", "instrument_id", "as_of"),
        {"comment": "价格快照表：保存用于估值、提醒和研究回放的行情点"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="价格快照ID")
    instrument_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolio_instruments.id"), nullable=False, comment="标的ID")
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="价格时间")
    price: Mapped[float] = mapped_column(Float, nullable=False, comment="最新价格")
    change_pct: Mapped[float | None] = mapped_column(Float, comment="涨跌幅")
    source: Mapped[str | None] = mapped_column(String(80), comment="数据来源")
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="原始行情数据")


class ResearchReport(Base, TimestampMixin):
    """研究报告。"""

    __tablename__ = "portfolio_research_reports"
    __table_args__ = (
        Index("ix_portfolio_research_reports_instrument", "instrument_id"),
        {"comment": "研究报告表：保存 Agent 或人工生成的研究结论和证据引用"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="研报ID")
    instrument_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("portfolio_instruments.id"), comment="关联标的ID，可为空表示组合级报告")
    title: Mapped[str] = mapped_column(String(240), nullable=False, comment="报告标题")
    report_type: Mapped[str] = mapped_column(String(60), default="research", nullable=False, comment="报告类型：research/earnings/risk/portfolio等")
    summary: Mapped[str | None] = mapped_column(Text, comment="摘要")
    content_path: Mapped[str | None] = mapped_column(String(500), comment="报告文件路径")
    content: Mapped[str | None] = mapped_column(Text, comment="报告正文")
    rating: Mapped[str | None] = mapped_column(String(40), comment="评级或建议")
    confidence: Mapped[float | None] = mapped_column(Float, comment="置信度，0到1")
    evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False, comment="证据列表，例如工具调用、数据源、引用链接")
    generated_by: Mapped[str | None] = mapped_column(String(120), comment="生成来源：agent/user/system")


class TrackingRule(Base, TimestampMixin):
    """自动跟踪规则。"""

    __tablename__ = "portfolio_tracking_rules"
    __table_args__ = {"comment": "自动跟踪规则表：定义价格、事件、财报、新闻等触发条件"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="规则ID")
    instrument_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("portfolio_instruments.id"), comment="关联标的ID，为空表示组合级规则")
    name: Mapped[str] = mapped_column(String(160), nullable=False, comment="规则名称")
    rule_type: Mapped[str] = mapped_column(String(60), nullable=False, comment="规则类型：price/news/earnings/risk/rebalance等")
    condition: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="触发条件JSON")
    action: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="触发后的动作JSON")
    cadence: Mapped[str | None] = mapped_column(String(40), comment="检查频率：daily/weekly/monthly/on_event等")
    next_run_date: Mapped[datetime | None] = mapped_column(DateTime, comment="下次执行时间")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="是否启用")


class RuleTriggerEvent(Base, TimestampMixin):
    """规则触发记录。"""

    __tablename__ = "portfolio_rule_trigger_events"
    __table_args__ = {"comment": "规则触发事件表：记录自动跟踪规则的执行结果"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="事件ID")
    rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolio_tracking_rules.id"), nullable=False, comment="规则ID")
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, comment="触发时间")
    status: Mapped[str] = mapped_column(String(40), default="triggered", nullable=False, comment="执行状态")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="触发上下文")
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="执行结果")


class DecisionLog(Base, TimestampMixin):
    """投资决策日志。"""

    __tablename__ = "portfolio_decision_logs"
    __table_args__ = {"comment": "投资决策日志表：记录买入、卖出、观察、调仓等决策及理由"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="决策ID")
    instrument_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("portfolio_instruments.id"), comment="关联标的ID")
    decision_type: Mapped[str] = mapped_column(String(60), nullable=False, comment="决策类型：buy/sell/hold/watch/rebalance等")
    decision_date: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, comment="决策时间")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="决策标题")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, comment="决策依据")
    expected_outcome: Mapped[str | None] = mapped_column(Text, comment="预期结果")
    review_date: Mapped[datetime | None] = mapped_column(DateTime, comment="复盘时间")
    status: Mapped[str] = mapped_column(String(40), default="open", nullable=False, comment="状态：open/reviewed/closed")
    linked_report_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("portfolio_research_reports.id"), comment="关联研报ID")


class PositionImportJob(Base, TimestampMixin):
    """持仓截图导入任务。"""

    __tablename__ = "portfolio_position_import_jobs"
    __table_args__ = {"comment": "持仓截图导入任务表：保存截图解析、完整性校验、人工确认和落库状态"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="导入任务ID")
    filename: Mapped[str] = mapped_column(String(260), nullable=False, comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(600), nullable=False, comment="截图文件保存路径")
    content_type: Mapped[str | None] = mapped_column(String(120), comment="上传文件MIME类型")
    broker: Mapped[str | None] = mapped_column(String(120), comment="券商或截图来源")
    account_name: Mapped[str | None] = mapped_column(String(160), comment="账户名称")
    status: Mapped[str] = mapped_column(String(40), default="uploaded", nullable=False, comment="任务状态：uploaded/parsed/needs_review/ready_to_save/saved/failed")
    parser: Mapped[str] = mapped_column(String(80), default="vision", nullable=False, comment="解析方式：vision/manual/fallback")
    summary: Mapped[str | None] = mapped_column(Text, comment="解析摘要或人工说明")
    raw_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="模型或OCR返回的原始结构化结果")
    missing_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False, comment="任务级缺失字段列表")
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False, comment="任务级校验警告")
    saved_at: Mapped[datetime | None] = mapped_column(DateTime, comment="确认保存时间")
    items: Mapped[list["PositionImportItem"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class PositionImportItem(Base, TimestampMixin):
    """持仓截图导入明细。"""

    __tablename__ = "portfolio_position_import_items"
    __table_args__ = (
        Index("ix_portfolio_position_import_items_job", "job_id"),
        {"comment": "持仓截图导入明细表：保存每一行识别出的持仓，等待人工核实后落库"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id, comment="导入明细ID")
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("portfolio_position_import_jobs.id"), nullable=False, comment="导入任务ID")
    row_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False, comment="截图中的行序号")
    symbol: Mapped[str | None] = mapped_column(String(64), comment="交易代码")
    name: Mapped[str | None] = mapped_column(String(200), comment="标的名称")
    market: Mapped[str | None] = mapped_column(String(40), comment="市场代码")
    asset_class: Mapped[str | None] = mapped_column(String(40), comment="资产类别")
    currency: Mapped[str | None] = mapped_column(String(12), comment="币种")
    quantity: Mapped[float | None] = mapped_column(Float, comment="持仓数量")
    available_quantity: Mapped[float | None] = mapped_column(Float, comment="可用数量")
    avg_cost: Mapped[float | None] = mapped_column(Float, comment="成本价")
    cost_basis: Mapped[float | None] = mapped_column(Float, comment="持仓成本")
    market_price: Mapped[float | None] = mapped_column(Float, comment="当前价")
    market_value: Mapped[float | None] = mapped_column(Float, comment="市值")
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, comment="浮动盈亏")
    unrealized_pnl_pct: Mapped[float | None] = mapped_column(Float, comment="浮动盈亏比例")
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, comment="整行识别置信度，0到1")
    field_confidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="字段级置信度")
    source_text: Mapped[str | None] = mapped_column(Text, comment="识别来源文本")
    missing_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False, comment="该行缺失的必填字段")
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False, comment="该行校验警告")
    status: Mapped[str] = mapped_column(String(40), default="needs_review", nullable=False, comment="明细状态：needs_review/ready/saved/skipped")
    saved_position_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("portfolio_positions.id"), comment="保存后的持仓ID")
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, comment="该行原始解析结果")
    job: Mapped[PositionImportJob] = relationship(back_populates="items")
