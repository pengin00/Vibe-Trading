"""Agent tools for the investment workspace."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool


def _run(operation):
    try:
        from src.portfolio.db import session_scope

        with session_scope() as session:
            result = operation(session)
            return json.dumps({"status": "ok", "data": result}, ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _instrument_dict(i) -> dict[str, Any]:
    return {
        "id": i.id,
        "symbol": i.symbol,
        "name": i.name,
        "market": i.market,
        "asset_class": i.asset_class,
        "currency": i.currency,
        "sector": i.sector,
        "tags": i.tags,
        "thesis": i.thesis,
        "is_active": i.is_active,
    }


def _position_dict(session, p) -> dict[str, Any]:
    from src.portfolio import service

    metrics = service.position_metrics(session, p)
    return {
        "id": p.id,
        "account": p.account.name if p.account else None,
        "symbol": p.instrument.symbol if p.instrument else None,
        "name": p.instrument.name if p.instrument else None,
        "market": p.instrument.market if p.instrument else None,
        "quantity": p.quantity,
        "avg_cost": p.avg_cost,
        "cost_basis": p.cost_basis,
        "target_weight": p.target_weight,
        "stop_loss": p.stop_loss,
        "take_profit": p.take_profit,
        **metrics,
    }


class ListTrackedInstrumentsTool(BaseTool):
    name = "list_tracked_instruments"
    description = "列出投资工作台中需要持续跟踪的标的，包括关注列表和持仓标的。做金融研究前应优先调用。"
    parameters = {
        "type": "object",
        "properties": {
            "include_inactive": {"type": "boolean", "description": "是否包含已停用标的，默认 false"}
        },
        "required": [],
    }
    repeatable = True
    is_readonly = True

    def execute(self, include_inactive: bool = False) -> str:
        def op(session):
            from src.portfolio import service

            instruments = service.list_instruments(session, active=None if include_inactive else True)
            return [_instrument_dict(i) for i in instruments]

        return _run(op)


class ListPositionsTool(BaseTool):
    name = "list_portfolio_positions"
    description = "列出投资工作台中的当前持仓及估值/盈亏信息。研究组合或个股前应优先调用。"
    parameters = {"type": "object", "properties": {}, "required": []}
    repeatable = True
    is_readonly = True

    def execute(self) -> str:
        def op(session):
            from src.portfolio import service

            return [_position_dict(session, p) for p in service.list_positions(session)]

        return _run(op)


class GetPositionTool(BaseTool):
    name = "get_portfolio_position"
    description = "按交易代码查询单个持仓，返回成本、数量、止盈止损和最新估值信息。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易代码，例如 AAPL"},
            "market": {"type": "string", "description": "市场代码，默认 US"},
        },
        "required": ["symbol"],
    }
    repeatable = True
    is_readonly = True

    def execute(self, symbol: str, market: str = "US") -> str:
        def op(session):
            from sqlalchemy import select
            from sqlalchemy.orm import joinedload
            from src.portfolio import models as m
            from src.portfolio import service

            instrument = service.find_instrument(session, symbol, market)
            if not instrument:
                return None
            p = session.execute(
                select(m.Position)
                .options(joinedload(m.Position.instrument), joinedload(m.Position.account))
                .where(m.Position.instrument_id == instrument.id)
                .limit(1)
            ).scalar_one_or_none()
            return _position_dict(session, p) if p else None

        return _run(op)


class UpsertPositionTool(BaseTool):
    name = "upsert_portfolio_position"
    description = "创建或更新投资工作台持仓。适合把用户确认后的持仓数据写入系统。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易代码"},
            "name": {"type": "string", "description": "标的名称"},
            "market": {"type": "string", "description": "市场代码，默认 US"},
            "asset_class": {"type": "string", "description": "资产类别，默认 equity"},
            "currency": {"type": "string", "description": "计价币种，默认 USD"},
            "quantity": {"type": "number", "description": "当前持仓数量"},
            "avg_cost": {"type": "number", "description": "平均成本"},
            "target_weight": {"type": "number", "description": "目标仓位权重，0到1"},
            "stop_loss": {"type": "number", "description": "止损价"},
            "take_profit": {"type": "number", "description": "止盈价"},
            "notes": {"type": "string", "description": "备注"},
        },
        "required": ["symbol", "name", "quantity", "avg_cost"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        def op(session):
            from sqlalchemy import select
            from sqlalchemy.orm import joinedload
            from src.portfolio import models as m
            from src.portfolio import service
            from src.portfolio.schemas import InstrumentCreate, PositionCreate, PositionUpdate

            symbol = kwargs["symbol"].upper()
            market = kwargs.get("market", "US").upper()
            instrument = service.find_instrument(session, symbol, market)
            if not instrument:
                instrument = service.create_instrument(
                    session,
                    InstrumentCreate(
                        symbol=symbol,
                        name=kwargs["name"],
                        market=market,
                        asset_class=kwargs.get("asset_class", "equity"),
                        currency=kwargs.get("currency", "USD"),
                    ),
                )
            account = service.default_account(session)
            existing = session.execute(
                select(m.Position)
                .options(joinedload(m.Position.instrument), joinedload(m.Position.account))
                .where(m.Position.account_id == account.id, m.Position.instrument_id == instrument.id)
                .limit(1)
            ).scalar_one_or_none()
            payload = {
                "quantity": kwargs["quantity"],
                "avg_cost": kwargs["avg_cost"],
                "target_weight": kwargs.get("target_weight"),
                "stop_loss": kwargs.get("stop_loss"),
                "take_profit": kwargs.get("take_profit"),
                "notes": kwargs.get("notes"),
            }
            if existing:
                p = service.update_position(session, existing.id, PositionUpdate(**payload))
            else:
                p = service.create_position(session, PositionCreate(instrument_id=instrument.id, account_id=account.id, **payload))
            return _position_dict(session, p)

        return _run(op)


class AddResearchReportTool(BaseTool):
    name = "add_portfolio_research_report"
    description = "把研究报告摘要、正文、评级和证据写入投资工作台。生成研报后应调用。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易代码，可选"},
            "market": {"type": "string", "description": "市场代码，默认 US"},
            "title": {"type": "string", "description": "报告标题"},
            "summary": {"type": "string", "description": "摘要"},
            "content": {"type": "string", "description": "报告正文"},
            "rating": {"type": "string", "description": "评级或建议"},
            "confidence": {"type": "number", "description": "置信度，0到1"},
            "evidence": {"type": "array", "description": "证据列表", "items": {"type": "object"}},
        },
        "required": ["title"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        def op(session):
            from src.portfolio import service
            from src.portfolio.schemas import ResearchReportCreate

            instrument_id = None
            if kwargs.get("symbol"):
                instrument = service.find_instrument(session, kwargs["symbol"], kwargs.get("market", "US"))
                instrument_id = instrument.id if instrument else None
            report = service.create_research_report(
                session,
                ResearchReportCreate(
                    instrument_id=instrument_id,
                    title=kwargs["title"],
                    summary=kwargs.get("summary"),
                    content=kwargs.get("content"),
                    rating=kwargs.get("rating"),
                    confidence=kwargs.get("confidence"),
                    evidence=kwargs.get("evidence") or [],
                    generated_by="agent",
                ),
            )
            return {"id": report.id, "title": report.title}

        return _run(op)


class RecordDecisionTool(BaseTool):
    name = "record_portfolio_decision"
    description = "记录一条投资决策日志，包括买入、卖出、持有、观察或调仓。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易代码，可选"},
            "market": {"type": "string", "description": "市场代码，默认 US"},
            "decision_type": {"type": "string", "description": "决策类型：buy/sell/hold/watch/rebalance"},
            "title": {"type": "string", "description": "决策标题"},
            "rationale": {"type": "string", "description": "决策依据"},
            "expected_outcome": {"type": "string", "description": "预期结果"},
        },
        "required": ["decision_type", "title", "rationale"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        def op(session):
            from src.portfolio import service
            from src.portfolio.schemas import DecisionLogCreate

            instrument_id = None
            if kwargs.get("symbol"):
                instrument = service.find_instrument(session, kwargs["symbol"], kwargs.get("market", "US"))
                instrument_id = instrument.id if instrument else None
            decision = service.create_decision(session, DecisionLogCreate(instrument_id=instrument_id, **{
                k: kwargs.get(k) for k in ["decision_type", "title", "rationale", "expected_outcome"]
            }))
            return {"id": decision.id, "title": decision.title, "decision_type": decision.decision_type}

        return _run(op)


class AddTrackingRuleTool(BaseTool):
    name = "add_portfolio_tracking_rule"
    description = "为投资标的或组合创建自动跟踪规则，例如价格提醒、新闻跟踪、财报跟踪或风险复查。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "交易代码，可选"},
            "market": {"type": "string", "description": "市场代码，默认 US"},
            "name": {"type": "string", "description": "规则名称"},
            "rule_type": {"type": "string", "description": "规则类型：price/news/earnings/risk/rebalance"},
            "condition": {"type": "object", "description": "触发条件JSON"},
            "action": {"type": "object", "description": "触发后的动作JSON"},
            "cadence": {"type": "string", "description": "检查频率"},
        },
        "required": ["name", "rule_type"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        def op(session):
            from src.portfolio import service
            from src.portfolio.schemas import TrackingRuleCreate

            instrument_id = None
            if kwargs.get("symbol"):
                instrument = service.find_instrument(session, kwargs["symbol"], kwargs.get("market", "US"))
                instrument_id = instrument.id if instrument else None
            rule = service.create_tracking_rule(
                session,
                TrackingRuleCreate(
                    instrument_id=instrument_id,
                    name=kwargs["name"],
                    rule_type=kwargs["rule_type"],
                    condition=kwargs.get("condition") or {},
                    action=kwargs.get("action") or {},
                    cadence=kwargs.get("cadence"),
                ),
            )
            return {"id": rule.id, "name": rule.name, "rule_type": rule.rule_type}

        return _run(op)


class RunPortfolioAutopilotTool(BaseTool):
    name = "run_portfolio_autopilot"
    description = "运行一次投资工作台自动研究：优先读取持仓和关注标的，刷新价格，执行跟踪规则，并写入自动研究简报。"
    parameters = {
        "type": "object",
        "properties": {
            "max_targets": {"type": "integer", "description": "最多处理的标的数量，默认 10"},
            "create_reports": {"type": "boolean", "description": "是否写入自动研究简报，默认 true"},
            "refresh_prices": {"type": "boolean", "description": "是否尝试刷新价格，默认 true"},
        },
        "required": [],
    }
    repeatable = True
    is_readonly = False

    def execute(self, max_targets: int = 10, create_reports: bool = True, refresh_prices: bool = True) -> str:
        try:
            from src.portfolio import autopilot

            result = autopilot.run_once(
                max_targets=max_targets,
                create_reports=create_reports,
                price_provider=autopilot.default_price_provider if refresh_prices else None,
            )
            return json.dumps({"status": result.status, "data": result.as_dict()}, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
