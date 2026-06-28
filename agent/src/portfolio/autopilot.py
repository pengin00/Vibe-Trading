"""Automated research loop for the Investment Workspace.

The autopilot is deliberately research-only: it reads tracked instruments and
positions, evaluates lightweight tracking rules, writes audit events, and saves
deterministic quick-update reports. LLM/swarm escalation can be layered on top
of the saved events without making scheduled jobs unexpectedly expensive.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, or_, select

from src.live.runtime.scheduler import Job, Scheduler
from src.portfolio import models as m
from src.portfolio import schemas as s
from src.portfolio import service
from src.portfolio.db import session_scope

logger = logging.getLogger(__name__)

PriceProvider = Callable[[m.Instrument], dict[str, Any] | None]


@dataclass
class ResearchTarget:
    """One instrument selected for scheduled research."""

    instrument: m.Instrument
    source: str
    priority: int
    position: m.Position | None = None
    watchlist: m.WatchlistItem | None = None


@dataclass
class AutopilotRunResult:
    """Summary of one portfolio autopilot run."""

    status: str
    started_at: datetime
    finished_at: datetime
    targets: list[dict[str, Any]] = field(default_factory=list)
    price_snapshots: list[str] = field(default_factory=list)
    triggered_events: list[str] = field(default_factory=list)
    research_reports: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "targets": self.targets,
            "price_snapshots": self.price_snapshots,
            "triggered_events": self.triggered_events,
            "research_reports": self.research_reports,
            "errors": self.errors,
        }


def collect_research_targets(session, *, max_targets: int = 10) -> list[ResearchTarget]:
    """Collect active positions and watchlist items, with holdings first."""

    by_instrument: dict[str, ResearchTarget] = {}
    positions = service.list_positions(session)
    for position in positions:
        if not position.instrument or not position.instrument.is_active:
            continue
        by_instrument[position.instrument_id] = ResearchTarget(
            instrument=position.instrument,
            position=position,
            source="position",
            priority=0,
        )

    watchlist_items = service.list_watchlist(session)
    for item in watchlist_items:
        instrument = item.instrument
        if not instrument or not instrument.is_active or item.status in {"paused", "closed", "archived"}:
            continue
        existing = by_instrument.get(item.instrument_id)
        if existing:
            existing.watchlist = item
            existing.source = "position+watchlist"
            existing.priority = min(existing.priority, item.priority)
            continue
        by_instrument[item.instrument_id] = ResearchTarget(
            instrument=instrument,
            watchlist=item,
            source="watchlist",
            priority=max(1, item.priority),
        )

    targets = sorted(
        by_instrument.values(),
        key=lambda target: (
            target.priority,
            0 if target.position is not None else 1,
            target.instrument.market,
            target.instrument.symbol,
        ),
    )
    return targets[: max(1, max_targets)]


def latest_price(session, instrument_id: str) -> float | None:
    return session.execute(
        select(m.PriceSnapshot.price)
        .where(m.PriceSnapshot.instrument_id == instrument_id)
        .order_by(desc(m.PriceSnapshot.as_of))
        .limit(1)
    ).scalar_one_or_none()


def default_price_provider(instrument: m.Instrument) -> dict[str, Any] | None:
    """Best-effort quote fetcher.

    Network and vendor failures are non-fatal. Returning ``None`` lets the
    autopilot still produce a report from existing snapshots and cost data.
    """

    symbol = instrument.symbol
    if instrument.market.upper() == "US" and "." not in symbol:
        symbol = f"{symbol}.US"
    if instrument.market.upper() == "HK" and symbol.isdigit():
        symbol = f"{symbol.zfill(4)}.HK"

    try:
        from src.market_data import fetch_market_data

        end = datetime.utcnow().date()
        start = end - timedelta(days=7)
        payload = fetch_market_data(
            codes=[symbol],
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            source=instrument.data_source or "auto",
            interval="1D",
            max_rows=0,
        )
        rows = payload.get(symbol) or payload.get(instrument.symbol)
        if isinstance(rows, dict):
            rows = rows.get("data")
        if isinstance(rows, list) and rows:
            last = rows[-1]
            price = last.get("close") or last.get("Close")
            if price is not None:
                return {
                    "price": float(price),
                    "change_pct": None,
                    "source": f"market_data:{instrument.data_source or 'auto'}",
                    "raw": {"symbol": symbol, "bar": last},
                }
    except Exception as exc:
        logger.info("portfolio autopilot shared loader failed for %s: %s", instrument.symbol, exc)

    try:
        import yfinance as yf
    except Exception:
        return None

    yf_symbol = symbol[:-3] if symbol.endswith(".US") else symbol
    try:
        history = yf.Ticker(yf_symbol).history(period="2d")
    except Exception as exc:
        logger.info("portfolio autopilot price fetch failed for %s: %s", instrument.symbol, exc)
        return None
    if history.empty:
        return None
    last = history.iloc[-1]
    previous = history.iloc[-2] if len(history) > 1 else None
    price = float(last.get("Close"))
    change_pct = None
    if previous is not None:
        prev_close = float(previous.get("Close") or 0)
        if prev_close:
            change_pct = price / prev_close - 1
    return {"price": price, "change_pct": change_pct, "source": "yfinance:fallback", "raw": {"symbol": yf_symbol}}


def refresh_prices(
    session,
    targets: list[ResearchTarget],
    *,
    price_provider: PriceProvider | None = default_price_provider,
) -> list[m.PriceSnapshot]:
    snapshots: list[m.PriceSnapshot] = []
    if price_provider is None:
        return snapshots
    for target in targets:
        quote = price_provider(target.instrument)
        if not quote or quote.get("price") is None:
            continue
        snapshot = service.add_price_snapshot(
            session,
            s.PriceSnapshotCreate(
                instrument_id=target.instrument.id,
                as_of=datetime.utcnow(),
                price=float(quote["price"]),
                change_pct=quote.get("change_pct"),
                source=quote.get("source") or "autopilot",
                raw=quote.get("raw") or {},
            ),
        )
        snapshots.append(snapshot)
    return snapshots


def _condition_triggered(condition: dict[str, Any], *, price: float | None, metrics: dict[str, Any]) -> tuple[bool, str]:
    if not condition:
        return True, "scheduled"
    if price is not None:
        if condition.get("price_below") is not None and price <= float(condition["price_below"]):
            return True, f"price <= {condition['price_below']}"
        if condition.get("price_above") is not None and price >= float(condition["price_above"]):
            return True, f"price >= {condition['price_above']}"
    pnl_pct = metrics.get("unrealized_pnl_pct")
    if pnl_pct is not None:
        if condition.get("pnl_pct_below") is not None and pnl_pct <= float(condition["pnl_pct_below"]):
            return True, f"pnl_pct <= {condition['pnl_pct_below']}"
        if condition.get("pnl_pct_above") is not None and pnl_pct >= float(condition["pnl_pct_above"]):
            return True, f"pnl_pct >= {condition['pnl_pct_above']}"
    return False, "not_triggered"


def evaluate_tracking_rules(session, targets: list[ResearchTarget]) -> list[m.RuleTriggerEvent]:
    events: list[m.RuleTriggerEvent] = []
    target_ids = [target.instrument.id for target in targets]
    if not target_ids:
        return events
    rules = list(
        session.execute(
            select(m.TrackingRule).where(
                m.TrackingRule.is_enabled == True,  # noqa: E712
                or_(m.TrackingRule.instrument_id.is_(None), m.TrackingRule.instrument_id.in_(target_ids)),
            )
        ).scalars()
    )
    target_by_id = {target.instrument.id: target for target in targets}
    for rule in rules:
        scoped_targets = targets if rule.instrument_id is None else [target_by_id[rule.instrument_id]]
        for target in scoped_targets:
            price = latest_price(session, target.instrument.id)
            metrics = service.position_metrics(session, target.position) if target.position is not None else {}
            triggered, reason = _condition_triggered(rule.condition or {}, price=price, metrics=metrics)
            if not triggered:
                continue
            event = m.RuleTriggerEvent(
                rule_id=rule.id,
                status="triggered",
                payload={
                    "instrument_id": target.instrument.id,
                    "symbol": target.instrument.symbol,
                    "market": target.instrument.market,
                    "price": price,
                    "reason": reason,
                    "condition": rule.condition or {},
                },
                result={"action": rule.action or {}, "handled_by": "portfolio_autopilot"},
            )
            session.add(event)
            session.flush()
            events.append(event)
    return events


def _watchlist_alert_reasons(target: ResearchTarget, price: float | None) -> list[str]:
    item = target.watchlist
    if item is None or price is None:
        return []
    reasons: list[str] = []
    if item.alert_price_low is not None and price <= item.alert_price_low:
        reasons.append(f"价格低于关注下沿 {item.alert_price_low:g}")
    if item.alert_price_high is not None and price >= item.alert_price_high:
        reasons.append(f"价格高于关注上沿 {item.alert_price_high:g}")
    return reasons


def create_quick_research_report(
    session,
    target: ResearchTarget,
    *,
    triggered_events: list[m.RuleTriggerEvent],
) -> m.ResearchReport:
    instrument = target.instrument
    price = latest_price(session, instrument.id)
    metrics = service.position_metrics(session, target.position) if target.position is not None else {}
    event_reasons = [
        event.payload.get("reason")
        for event in triggered_events
        if event.payload.get("instrument_id") == instrument.id
    ]
    event_reasons.extend(_watchlist_alert_reasons(target, price))
    title = f"{instrument.symbol} 自动研究简报"
    pnl = metrics.get("unrealized_pnl")
    pnl_pct = metrics.get("unrealized_pnl_pct")
    summary_parts = [
        f"{instrument.symbol} ({instrument.market}) 来源：{target.source}",
        f"最新价：{price:g}" if price is not None else "最新价：暂无价格快照",
    ]
    if target.position is not None:
        summary_parts.append(
            "持仓："
            f"{target.position.quantity:g} 股/份，成本 {target.position.avg_cost:g}，"
            f"浮盈亏 {pnl:g} ({pnl_pct:.2%})"
        )
    if event_reasons:
        summary_parts.append("触发：" + "；".join(str(reason) for reason in event_reasons if reason))
    else:
        summary_parts.append("触发：无重大规则命中，按计划复盘")
    content = "\n".join(f"- {part}" for part in summary_parts)
    report = service.create_research_report(
        session,
        s.ResearchReportCreate(
            instrument_id=instrument.id,
            title=title,
            report_type="auto_update",
            summary="；".join(summary_parts),
            content=content,
            rating="review",
            confidence=0.65,
            evidence=[
                {
                    "source": "portfolio_autopilot",
                    "target_source": target.source,
                    "price": price,
                    "event_count": len(event_reasons),
                }
            ],
            generated_by="portfolio_autopilot",
        ),
    )
    return report


def run_once(
    *,
    max_targets: int = 10,
    price_provider: PriceProvider | None = default_price_provider,
    create_reports: bool = True,
) -> AutopilotRunResult:
    started = datetime.utcnow()
    errors: list[str] = []
    try:
        with session_scope() as session:
            service.ensure_default_tracking_rules(session)
            targets = collect_research_targets(session, max_targets=max_targets)
            snapshots = refresh_prices(session, targets, price_provider=price_provider)
            events = evaluate_tracking_rules(session, targets)
            reports = [
                create_quick_research_report(session, target, triggered_events=events)
                for target in targets
            ] if create_reports else []
            finished = datetime.utcnow()
            return AutopilotRunResult(
                status="ok",
                started_at=started,
                finished_at=finished,
                targets=[
                    {
                        "instrument_id": target.instrument.id,
                        "symbol": target.instrument.symbol,
                        "market": target.instrument.market,
                        "source": target.source,
                    }
                    for target in targets
                ],
                price_snapshots=[snapshot.id for snapshot in snapshots],
                triggered_events=[event.id for event in events],
                research_reports=[report.id for report in reports],
            )
    except Exception as exc:
        logger.exception("portfolio autopilot run failed")
        errors.append(str(exc))
    finished = datetime.utcnow()
    return AutopilotRunResult("error", started, finished, errors=errors)


class AutopilotRunner:
    """Small in-process scheduler wrapper used by the API server."""

    def __init__(self) -> None:
        self._scheduler: Scheduler | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None

    async def _on_fire(self, job: Job) -> None:
        payload = job.payload or {}
        result = await asyncio.to_thread(
            run_once,
            max_targets=int(payload.get("max_targets") or 10),
            create_reports=bool(payload.get("create_reports", True)),
        )
        self.last_result = result.as_dict()

    def start(self, *, interval_seconds: int = 3600, max_targets: int = 10, run_immediately: bool = False) -> dict[str, Any]:
        if self._scheduler is not None:
            self.stop()
        interval_ms = max(60, int(interval_seconds)) * 1000
        next_run_at = int(datetime.utcnow().timestamp() * 1000)
        if not run_immediately:
            next_run_at += interval_ms
        job = Job(
            id="portfolio-autopilot",
            next_run_at=next_run_at,
            schedule=f"interval:{interval_ms}",
            payload={"max_targets": max_targets, "create_reports": True},
        )

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._scheduler = Scheduler(self._on_fire)
            self._scheduler.add_job(job)
            loop.call_soon(self._scheduler.start)
            loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, name="portfolio-autopilot", daemon=True)
        self._thread.start()
        return {"status": "scheduled", "interval_seconds": interval_seconds, "max_targets": max_targets}

    def stop(self) -> dict[str, Any]:
        if self._loop is not None:
            scheduler = self._scheduler
            loop = self._loop

            async def _shutdown() -> None:
                if scheduler is not None:
                    await scheduler.stop()
                loop.stop()

            asyncio.run_coroutine_threadsafe(_shutdown(), loop)
        self._scheduler = None
        self._loop = None
        self._thread = None
        return {"status": "stopped"}

    def status(self) -> dict[str, Any]:
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "last_result": self.last_result,
        }


api_runner = AutopilotRunner()
