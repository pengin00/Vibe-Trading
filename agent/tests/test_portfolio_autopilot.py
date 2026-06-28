from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.context import ContextBuilder
from src.agent.memory import WorkspaceMemory
from src.agent.tools import ToolRegistry
from src.portfolio import autopilot, service
from src.portfolio import db as portfolio_db
from src.portfolio import schemas as s
from src.portfolio.db import session_scope


@pytest.fixture()
def portfolio_db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{tmp_path / 'portfolio.db'}"
    monkeypatch.setenv("VIBE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    portfolio_db._ENGINE = None
    portfolio_db._SESSIONMAKER = None
    portfolio_db._INITIALIZED = False
    yield url
    portfolio_db._ENGINE = None
    portfolio_db._SESSIONMAKER = None
    portfolio_db._INITIALIZED = False


def test_collect_research_targets_prioritizes_positions(portfolio_db_url: str) -> None:
    with session_scope() as session:
        held = service.create_instrument(session, s.InstrumentCreate(symbol="AAPL", name="Apple"))
        watched = service.create_instrument(session, s.InstrumentCreate(symbol="MSFT", name="Microsoft"))
        service.create_position(session, s.PositionCreate(instrument_id=held.id, quantity=3, avg_cost=100))
        service.create_watchlist_item(session, s.WatchlistItemCreate(instrument_id=watched.id, priority=1))

        targets = autopilot.collect_research_targets(session)

    assert [target.instrument.symbol for target in targets] == ["AAPL", "MSFT"]
    assert targets[0].source == "position"


def test_run_once_writes_rule_event_and_report(portfolio_db_url: str) -> None:
    with session_scope() as session:
        instrument = service.create_instrument(session, s.InstrumentCreate(symbol="NVDA", name="Nvidia"))
        service.create_watchlist_item(session, s.WatchlistItemCreate(instrument_id=instrument.id, priority=2))
        service.create_tracking_rule(
            session,
            s.TrackingRuleCreate(
                instrument_id=instrument.id,
                name="Price breakout",
                rule_type="price",
                condition={"price_above": 120},
                action={"research": "quick_update"},
            ),
        )

    def quote(_instrument):
        return {"price": 125.0, "source": "test", "raw": {}}

    result = autopilot.run_once(max_targets=5, price_provider=quote)

    assert result.status == "ok"
    assert len(result.targets) == 1
    assert len(result.price_snapshots) == 1
    assert len(result.triggered_events) == 1
    assert len(result.research_reports) == 1


def test_context_prompt_includes_portfolio_first_policy() -> None:
    registry = ToolRegistry()
    builder = ContextBuilder(registry, WorkspaceMemory())

    prompt = builder.build_system_prompt("分析我的持仓要不要加仓")

    assert "Investment Workspace / portfolio-first research" in prompt
    assert "list_portfolio_positions" in prompt
    assert "Automatic research tasks must prioritize open positions first" in prompt
