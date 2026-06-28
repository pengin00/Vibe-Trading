"""Service layer for investment workspace CRUD and portfolio calculations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import joinedload

from . import models as m


def _values(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=True)
    return dict(payload)


def _latest_price(session, instrument_id: str) -> float | None:
    row = session.execute(
        select(m.PriceSnapshot.price)
        .where(m.PriceSnapshot.instrument_id == instrument_id)
        .order_by(desc(m.PriceSnapshot.as_of))
        .limit(1)
    ).scalar_one_or_none()
    return row


def position_metrics(session, position: m.Position) -> dict[str, float | None]:
    price = _latest_price(session, position.instrument_id) or position.avg_cost
    market_value = float(position.quantity or 0) * float(price or 0)
    cost_basis = float(position.cost_basis or 0)
    pnl = market_value - cost_basis
    pnl_pct = pnl / cost_basis if cost_basis else 0.0
    return {
        "market_price": price,
        "market_value": market_value,
        "unrealized_pnl": pnl,
        "unrealized_pnl_pct": pnl_pct,
    }


def default_account(session) -> m.PortfolioAccount:
    account = session.execute(
        select(m.PortfolioAccount).where(m.PortfolioAccount.name == "Default Manual Account").limit(1)
    ).scalar_one_or_none()
    if account:
        return account
    account = m.PortfolioAccount(name="Default Manual Account", broker="manual", account_type="manual")
    session.add(account)
    session.flush()
    return account


def list_accounts(session) -> list[m.PortfolioAccount]:
    return list(session.execute(select(m.PortfolioAccount).order_by(m.PortfolioAccount.created_at)).scalars())


def create_account(session, payload) -> m.PortfolioAccount:
    account = m.PortfolioAccount(**_values(payload))
    session.add(account)
    session.flush()
    return account


def list_instruments(session, q: str | None = None, active: bool | None = None) -> list[m.Instrument]:
    stmt = select(m.Instrument).order_by(m.Instrument.market, m.Instrument.symbol)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where((m.Instrument.symbol.ilike(needle)) | (m.Instrument.name.ilike(needle)))
    if active is not None:
        stmt = stmt.where(m.Instrument.is_active == active)
    return list(session.execute(stmt).scalars())


def get_instrument(session, instrument_id: str) -> m.Instrument | None:
    return session.get(m.Instrument, instrument_id)


def find_instrument(session, symbol: str, market: str = "US") -> m.Instrument | None:
    return session.execute(
        select(m.Instrument).where(m.Instrument.symbol == symbol.upper(), m.Instrument.market == market.upper()).limit(1)
    ).scalar_one_or_none()


def create_instrument(session, payload) -> m.Instrument:
    data = _values(payload)
    data["symbol"] = data["symbol"].upper()
    data["market"] = data.get("market", "US").upper()
    instrument = m.Instrument(**data)
    session.add(instrument)
    session.flush()
    return instrument


def update_instrument(session, instrument_id: str, payload) -> m.Instrument | None:
    instrument = get_instrument(session, instrument_id)
    if not instrument:
        return None
    for key, value in _values(payload).items():
        if key in {"symbol", "market"} and isinstance(value, str):
            value = value.upper()
        setattr(instrument, key, value)
    session.flush()
    return instrument


def delete_instrument(session, instrument_id: str) -> bool:
    instrument = get_instrument(session, instrument_id)
    if not instrument:
        return False
    instrument.is_active = False
    session.flush()
    return True


def list_watchlist(session) -> list[m.WatchlistItem]:
    return list(
        session.execute(
            select(m.WatchlistItem)
            .options(joinedload(m.WatchlistItem.instrument))
            .order_by(m.WatchlistItem.priority, m.WatchlistItem.created_at)
        ).scalars()
    )


def create_watchlist_item(session, payload) -> m.WatchlistItem:
    item = m.WatchlistItem(**_values(payload))
    session.add(item)
    session.flush()
    return item


def update_watchlist_item(session, item_id: str, payload) -> m.WatchlistItem | None:
    item = session.get(m.WatchlistItem, item_id)
    if not item:
        return None
    for key, value in _values(payload).items():
        setattr(item, key, value)
    session.flush()
    return item


def delete_watchlist_item(session, item_id: str) -> bool:
    item = session.get(m.WatchlistItem, item_id)
    if not item:
        return False
    session.delete(item)
    session.flush()
    return True


def list_positions(session) -> list[m.Position]:
    return list(
        session.execute(
            select(m.Position)
            .options(joinedload(m.Position.instrument), joinedload(m.Position.account))
            .order_by(m.Position.updated_at.desc())
        ).scalars()
    )


def get_position(session, position_id: str) -> m.Position | None:
    return session.execute(
        select(m.Position)
        .options(joinedload(m.Position.instrument), joinedload(m.Position.account))
        .where(m.Position.id == position_id)
    ).scalar_one_or_none()


def create_position(session, payload) -> m.Position:
    data = _values(payload)
    if not data.get("account_id"):
        data["account_id"] = default_account(session).id
    if data.get("cost_basis") is None:
        data["cost_basis"] = float(data.get("quantity") or 0) * float(data.get("avg_cost") or 0)
    position = m.Position(**data, opened_at=datetime.utcnow())
    session.add(position)
    session.flush()
    return get_position(session, position.id) or position


def update_position(session, position_id: str, payload) -> m.Position | None:
    position = get_position(session, position_id)
    if not position:
        return None
    data = _values(payload)
    for key, value in data.items():
        setattr(position, key, value)
    if ("quantity" in data or "avg_cost" in data) and "cost_basis" not in data:
        position.cost_basis = float(position.quantity or 0) * float(position.avg_cost or 0)
    session.flush()
    return get_position(session, position.id)


def add_position_lot(session, payload) -> tuple[m.PositionLot, m.Position]:
    data = _values(payload)
    if data.get("trade_date") is None:
        data["trade_date"] = datetime.utcnow()
    lot = m.PositionLot(**data)
    position = get_position(session, lot.position_id)
    if position is None:
        raise ValueError("Position not found")
    signed_qty = lot.quantity if lot.side in {"buy", "transfer_in", "adjustment"} else -lot.quantity
    old_qty = float(position.quantity or 0)
    old_cost = float(position.cost_basis or 0)
    if signed_qty >= 0:
        new_cost = old_cost + lot.quantity * lot.price + lot.fees
    else:
        reduce_cost = (old_cost / old_qty * lot.quantity) if old_qty else 0
        new_cost = max(0.0, old_cost - reduce_cost)
    new_qty = old_qty + signed_qty
    position.quantity = new_qty
    position.cost_basis = new_cost
    position.avg_cost = new_cost / new_qty if new_qty else 0.0
    session.add(lot)
    session.flush()
    return lot, position


def add_price_snapshot(session, payload) -> m.PriceSnapshot:
    data = _values(payload)
    if data.get("as_of") is None:
        data["as_of"] = datetime.utcnow()
    snapshot = m.PriceSnapshot(**data)
    session.add(snapshot)
    session.flush()
    return snapshot


def list_research_reports(session, instrument_id: str | None = None, limit: int = 20) -> list[m.ResearchReport]:
    stmt = select(m.ResearchReport).order_by(m.ResearchReport.created_at.desc()).limit(limit)
    if instrument_id:
        stmt = stmt.where(m.ResearchReport.instrument_id == instrument_id)
    return list(session.execute(stmt).scalars())


def create_research_report(session, payload) -> m.ResearchReport:
    report = m.ResearchReport(**_values(payload))
    session.add(report)
    session.flush()
    return report


def list_tracking_rules(session) -> list[m.TrackingRule]:
    return list(session.execute(select(m.TrackingRule).order_by(m.TrackingRule.created_at.desc())).scalars())


def create_tracking_rule(session, payload) -> m.TrackingRule:
    rule = m.TrackingRule(**_values(payload))
    session.add(rule)
    session.flush()
    return rule


def update_tracking_rule(session, rule_id: str, payload) -> m.TrackingRule | None:
    rule = session.get(m.TrackingRule, rule_id)
    if not rule:
        return None
    for key, value in _values(payload).items():
        setattr(rule, key, value)
    session.flush()
    return rule


def list_decisions(session, instrument_id: str | None = None, limit: int = 30) -> list[m.DecisionLog]:
    stmt = select(m.DecisionLog).order_by(m.DecisionLog.decision_date.desc()).limit(limit)
    if instrument_id:
        stmt = stmt.where(m.DecisionLog.instrument_id == instrument_id)
    return list(session.execute(stmt).scalars())


def create_decision(session, payload) -> m.DecisionLog:
    decision = m.DecisionLog(**_values(payload))
    session.add(decision)
    session.flush()
    return decision


def dashboard(session) -> dict[str, Any]:
    positions = list_positions(session)
    total_cost = sum(float(p.cost_basis or 0) for p in positions)
    total_value = sum(position_metrics(session, p)["market_value"] or 0 for p in positions)
    return {
        "accounts": session.scalar(select(func.count(m.PortfolioAccount.id))) or 0,
        "instruments": session.scalar(select(func.count(m.Instrument.id))) or 0,
        "watchlist_items": session.scalar(select(func.count(m.WatchlistItem.id))) or 0,
        "positions": len(positions),
        "total_cost_basis": total_cost,
        "total_market_value": total_value,
        "total_unrealized_pnl": total_value - total_cost,
        "recent_reports": list_research_reports(session, limit=5),
    }
