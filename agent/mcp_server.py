#!/usr/bin/env python3
"""Vibe-Trading MCP Server — expose finance research tools to any MCP client.

Works with OpenClaw, Claude Desktop, Cursor, and any MCP-compatible client.
Zero API key required for HK/US/crypto research markets (yfinance, OKX,
AKShare are free). Trading connector tools are profile-scoped and require the
selected connector's own local app or OAuth setup.

Usage:
    python mcp_server.py                    # stdio transport (default)
    python mcp_server.py --transport sse    # SSE transport for web clients

OpenClaw config (~/.openclaw/config.yaml):
    skills:
      - name: vibe-trading
        command: python /path/to/agent/mcp_server.py

Claude Desktop config:
    {
      "mcpServers": {
        "vibe-trading": {
          "command": "python",
          "args": ["/path/to/agent/mcp_server.py"]
        }
      }
    }
"""

from __future__ import annotations

# ruff: noqa: E402

import json
import logging
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

# Ensure agent/ is on sys.path
AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))


def _ensure_mcp_environment() -> None:
    """Load local .env and provide local portfolio DB defaults for MCP entrypoints."""
    try:
        from src.providers.llm import _ensure_dotenv

        _ensure_dotenv()
    except Exception:  # noqa: BLE001 - MCP should still expose non-LLM tools
        pass
    if not os.getenv("DATABASE_URL") and not os.getenv("VIBE_DATABASE_URL"):
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "vibe_trading")
        user = os.getenv("POSTGRES_USER", "vibe")
        password = os.getenv("POSTGRES_PASSWORD", "vibe_dev_password")
        os.environ["DATABASE_URL"] = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


_ensure_mcp_environment()

from fastmcp import Context, FastMCP
from src.market_data import (
    DEFAULT_MAX_ROWS,
    cap_rows,
    detect_source,
    fetch_market_data_json,
    get_loader,
)

mcp = FastMCP("Vibe-Trading")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------

_skills_loader = None
_registry = None
_goal_store = None
_mcp_session_service = None
_include_shell_tools = True


def _env_shell_tools_enabled() -> bool:
    """Return whether shell tools were explicitly enabled for network MCP."""
    return os.getenv("VIBE_TRADING_ENABLE_SHELL_TOOLS", "").strip().lower() in {"1", "true", "yes", "on"}


def _get_skills_loader():
    global _skills_loader
    if _skills_loader is None:
        from src.agent.skills import SkillsLoader

        _skills_loader = SkillsLoader()
    return _skills_loader


def _get_registry():
    global _registry
    if _registry is None:
        from src.tools import build_registry

        _registry = build_registry(include_shell_tools=_include_shell_tools)
    return _registry


def _get_goal_store():
    """Return the shared finance goal store."""
    global _goal_store
    if _goal_store is None:
        from src.goal import GoalStore

        _goal_store = GoalStore()
    return _goal_store


def _get_mcp_session_service():
    """Return a lightweight SessionService for MCP-created UI sessions."""
    global _mcp_session_service
    if _mcp_session_service is None:
        from src.session.events import EventBus
        from src.session.service import SessionService
        from src.session.store import SessionStore

        _mcp_session_service = SessionService(
            store=SessionStore(base_dir=AGENT_DIR / "sessions"),
            event_bus=EventBus(),
            runs_dir=AGENT_DIR / "runs",
        )
    return _mcp_session_service


def _safe_ui_session_id(external_session_id: str) -> str:
    """Map an external MCP session id to a Vibe-Trading path-safe id."""
    import hashlib

    raw = str(external_session_id or "").strip()
    if not raw:
        raise ValueError("session_id is required")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-")
    safe = re.sub(r"-{2,}", "-", safe)
    if not safe:
        safe = "mcp-session"
    if safe == raw and len(safe) <= 128:
        return safe
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    prefix = safe[:117].strip("-_") or "mcp-session"
    candidate = f"{prefix}-{digest}"
    return candidate[:128].strip("-_")


def _generate_session_title(objective: str, ui_summary: str = "") -> str:
    """Generate a compact UI title from an MCP research objective."""
    text = (ui_summary or objective or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"^(请|帮我|麻烦|继续|接着|再)?\s*(分析|研究|看一下|看看|做一下|梳理|评估)\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(r"^(关于|一下|下)\s*", "", text).strip()
    if not text:
        return "MCP Research"
    if len(text) <= 28:
        return text
    separators = ["，", ",", "。", ".", "；", ";", "：", ":", " - ", " -- "]
    cut = len(text)
    for sep in separators:
        pos = text.find(sep)
        if 8 <= pos <= 36:
            cut = min(cut, pos)
    if cut != len(text):
        text = text[:cut].strip()
    if len(text) > 36:
        text = text[:34].rstrip() + "..."
    return text or "MCP Research"


def _session_matches_external_id(session: Any, external_session_id: str) -> bool:
    """Return whether a UI session is already associated with an external id."""
    external = str(external_session_id or "").strip()
    config = getattr(session, "config", {}) or {}
    aliases = config.get("external_session_aliases") or []
    return (
        session.session_id == external
        or session.session_id == _safe_ui_session_id(external)
        or config.get("external_session_id") == external
        or external in aliases
    )


def _find_session_by_external_id(external_session_id: str):
    """Find an existing UI session by exact id, mapped id, or MCP alias."""
    svc = _get_mcp_session_service()
    external = str(external_session_id or "").strip()
    for candidate in (external, _safe_ui_session_id(external)):
        session = svc.store.get_session(candidate)
        if session is not None:
            return session
    for session in svc.list_sessions(limit=500):
        if _session_matches_external_id(session, external):
            return session
    return None


def _attach_external_session_alias(session: Any, external_session_id: str) -> None:
    """Persist an external MCP id as an alias for a reused UI session."""
    from datetime import datetime

    external = str(external_session_id or "").strip()
    if not external:
        return
    config = dict(session.config or {})
    aliases = list(config.get("external_session_aliases") or [])
    if external != config.get("external_session_id") and external not in aliases:
        aliases.append(external)
        config["external_session_aliases"] = aliases[-20:]
        config.setdefault("source", "mcp")
        session.config = config
        session.updated_at = datetime.now().isoformat()
        _get_mcp_session_service().store.update_session(session)


def _ensure_ui_session(external_session_id: str, title: str = "", config: dict[str, Any] | None = None):
    """Create or return a UI-visible session for an external MCP session id."""
    from datetime import datetime

    from src.session.models import Session

    external = str(external_session_id or "").strip()
    ui_session_id = _safe_ui_session_id(external)
    svc = _get_mcp_session_service()
    session = _find_session_by_external_id(external)
    session_config = {
        "source": "mcp",
        "external_session_id": external,
        **(config or {}),
    }
    if session is None:
        session = Session(
            session_id=ui_session_id,
            title=(title or external or ui_session_id)[:120],
            config=session_config,
        )
        svc.store.create_session(session)
        svc._search_index.index_session(session.session_id, session.title)
        svc.event_bus.emit(
            session.session_id,
            "session.created",
            {"session_id": session.session_id, "title": session.title, "source": "mcp"},
        )
    else:
        changed = False
        if title and (not session.title or session.title in {external, ui_session_id, "MCP Research"}):
            session.title = title[:120]
            changed = True
        aliases = list((session.config or {}).get("external_session_aliases") or [])
        if external != (session.config or {}).get("external_session_id") and external not in aliases:
            aliases.append(external)
        merged_config = {**session.config, **session_config}
        if aliases:
            merged_config["external_session_aliases"] = aliases[-20:]
        if merged_config != session.config:
            session.config = merged_config
            changed = True
        if changed:
            session.updated_at = datetime.now().isoformat()
            svc.store.update_session(session)
            svc._search_index.index_session(session.session_id, session.title)
    return session


def _append_ui_message(session_id: str, role: str, content: str, metadata: dict[str, Any] | None = None):
    """Append a UI-visible message without triggering the agent loop."""
    from datetime import datetime

    from src.session.models import Message

    svc = _get_mcp_session_service()
    session = svc.store.get_session(session_id)
    if session is None:
        raise ValueError(f"Session {session_id} not found")
    message = Message(
        session_id=session_id,
        role=role,
        content=content,
        metadata=metadata or {},
    )
    svc.store.append_message(message)
    svc._search_index.index_message(session_id, role, content)
    session.updated_at = datetime.now().isoformat()
    svc.store.update_session(session)
    svc.event_bus.emit(
        session_id,
        "message.received",
        {"message_id": message.message_id, "role": role, "content": content, "source": "mcp"},
    )
    return message


def _session_similarity(session: Any, objective: str, ui_summary: str = "") -> float:
    """Score how likely a session is related to a new objective."""
    haystack = " ".join(
        [
            getattr(session, "title", "") or "",
            str((getattr(session, "config", {}) or {}).get("topic_key") or ""),
        ]
    ).lower()
    needle = " ".join([objective or "", ui_summary or ""]).lower().strip()
    if not haystack or not needle:
        return 0.0
    ratio = SequenceMatcher(None, haystack, needle).ratio()
    tokens = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]", needle, re.IGNORECASE))
    if not tokens:
        return ratio
    overlap = sum(1 for token in tokens if token in haystack) / len(tokens)
    return max(ratio, overlap)


def _json_ok(**payload: Any) -> str:
    """Return a standard MCP JSON success envelope."""
    return json.dumps({"status": "ok", **payload}, ensure_ascii=False, indent=2)


def _json_error(error: str, *, error_type: str = "error") -> str:
    """Return a standard MCP JSON error envelope."""
    return json.dumps(
        {"status": "error", "error_type": error_type, "error": error},
        ensure_ascii=False,
        indent=2,
    )


def _default_goal_criteria() -> list[str]:
    """Return the MVP finance protocol checklist."""
    from src.goal.context import default_goal_criteria

    return default_goal_criteria()


def _clean_list(value: list[str] | None) -> list[str]:
    """Strip empty list values from MCP payloads."""
    return [item.strip() for item in (value or []) if item and item.strip()]


def _blank_to_none(value: str | None) -> str | None:
    """Normalize blank MCP strings to None."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _audit_rows_from_payload(value: list[dict[str, Any]] | None):
    """Parse MCP completion audit rows."""
    from src.goal import AuditRow

    rows = []
    for item in value or []:
        criterion_id = str(item.get("criterion_id") or "").strip()
        result = str(item.get("result") or "").strip()
        if not criterion_id or not result:
            raise ValueError("audit rows require criterion_id and result")
        rows.append(
            AuditRow(
                criterion_id=criterion_id,
                result=result,
                evidence_ids=_clean_list(item.get("evidence_ids") or []),
                notes=str(item.get("notes") or ""),
            )
        )
    return rows


def _risk_tier_from_text(value: str):
    """Parse and validate goal risk tier."""
    from src.goal import RiskTier

    risk_tier = RiskTier(value)
    if risk_tier is RiskTier.LIVE_TRADING_OR_EXECUTION:
        raise ValueError("live trading or execution goals are not supported")
    return risk_tier


# ---------------------------------------------------------------------------
# Skill tools
# ---------------------------------------------------------------------------


@mcp.tool
def list_skills() -> str:
    """List all available finance skills with names and descriptions.

    Returns a JSON array of {name, description} for all loaded skills.
    Use load_skill(name) to get the full documentation for any skill.
    """
    loader = _get_skills_loader()
    skills = [{"name": s.name, "description": s.description} for s in loader.skills]
    return json.dumps(skills, ensure_ascii=False, indent=2)


@mcp.tool
def load_skill(name: str) -> str:
    """Load full documentation for a named finance skill.

    Each skill is a comprehensive knowledge document covering methodology,
    code templates, parameters, and examples. Use list_skills() first to
    discover available skills.

    Args:
        name: Skill name (e.g. 'strategy-generate', 'risk-analysis', 'technical-basic').
    """
    loader = _get_skills_loader()
    content = loader.get_content(name)
    if content.startswith("Error:"):
        return json.dumps({"status": "error", "error": content}, ensure_ascii=False)
    return json.dumps({"status": "ok", "skill": name, "content": content}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# UI session bridge tools
# ---------------------------------------------------------------------------


@mcp.tool
def ensure_ui_session(
    session_id: str,
    title: str = "",
    topic_key: str | None = None,
) -> str:
    """Create or return a Vibe-Trading UI session for an external MCP session.

    External clients such as OpenClaw may use ids that are not safe in REST
    paths, e.g. ``openclaw:vibe:cn:chip:industry-research``. This tool maps
    that id to a stable Vibe-Trading session id, creates ``session.json`` under
    ``agent/sessions/``, and returns both ids. Use the returned
    ``ui_session_id`` for deep links or REST paths; MCP goal tools accept either
    the original external id or the returned UI id.

    Args:
        session_id: External conversation/session id owned by the MCP client.
        title: Optional title shown in the Vibe-Trading Sessions UI.
        topic_key: Optional normalized topic key for cross-client bookkeeping.
    """
    try:
        session = _ensure_ui_session(
            session_id,
            title=title,
            config={"topic_key": _blank_to_none(topic_key)} if topic_key else {},
        )
        return _json_ok(
            external_session_id=session_id.strip(),
            ui_session_id=session.session_id,
            session=session.to_dict(),
        )
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


@mcp.tool
def append_ui_session_message(
    session_id: str,
    role: str,
    content: str,
    title: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    """Append a message to a Vibe-Trading UI session without running the agent.

    Use this from MCP clients to mirror user prompts, tool summaries, and final
    research answers into the Vibe-Trading Sessions UI. It does not call the
    Vibe-Trading agent loop; it only writes ``messages.jsonl`` and the search
    index.

    Args:
        session_id: External MCP id or a Vibe-Trading UI-safe session id.
        role: Message role: user, assistant, system, or tool.
        content: Message text to display and index.
        title: Optional title used when the UI session must be created first.
        metadata: Optional JSON metadata stored on the message.
    """
    try:
        role = role.strip().lower()
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError("role must be one of: user, assistant, system, tool")
        session = _ensure_ui_session(session_id, title=title)
        message = _append_ui_message(
            session.session_id,
            role,
            content,
            metadata={
                "source": "mcp",
                "external_session_id": session_id.strip(),
                **(metadata or {}),
            },
        )
        return _json_ok(
            external_session_id=session_id.strip(),
            ui_session_id=session.session_id,
            message=message.to_dict(),
        )
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


@mcp.tool
def list_ui_sessions(limit: int = 20, source: str = "") -> str:
    """List Vibe-Trading UI sessions visible in the Sessions page.

    This is a read-only MCP helper for clients such as OpenClaw to discover
    reusable Vibe-Trading sessions before starting a new research goal.

    Args:
        limit: Maximum sessions to return. Defaults to 20, capped at 100.
        source: Optional source filter, e.g. ``mcp``.
    """
    try:
        limit = max(1, min(int(limit), 100))
        source_filter = source.strip().lower()
        sessions = []
        for session in _get_mcp_session_service().list_sessions(limit=500):
            config = session.config or {}
            if source_filter and str(config.get("source") or "").lower() != source_filter:
                continue
            sessions.append(session.to_dict())
            if len(sessions) >= limit:
                break
        return _json_ok(count=len(sessions), sessions=sessions)
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


@mcp.tool
def search_ui_sessions(query: str, max_results: int = 5) -> str:
    """Search Vibe-Trading UI sessions using the local FTS5 session index.

    Args:
        query: Search keywords or natural-language topic.
        max_results: Maximum matching sessions to return. Defaults to 5,
            capped at 100.
    """
    try:
        query = query.strip()
        if not query:
            raise ValueError("query is required")
        max_results = max(1, min(int(max_results), 100))
        from src.session.search import get_shared_index

        matches = [match.to_dict() for match in get_shared_index().search(query, max_sessions=max_results)]
        return _json_ok(query=query, count=len(matches), sessions=matches)
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


@mcp.tool
def find_or_create_session(
    external_session_id: str,
    objective: str,
    ui_summary: str = "",
    similarity_threshold: float = 0.55,
    max_candidates: int = 3,
) -> str:
    """Find a related Vibe-Trading UI session or create a new one.

    Use this before starting a research goal when a client wants one topic to
    reuse the same Vibe-Trading Session across multiple OpenClaw turns.
    Matching is conservative: exact external-id aliases win first, then FTS5
    search/title similarity candidates are considered. When an existing UI
    session is reused, the new external id is stored as an alias so later MCP
    calls with that external id resolve to the reused session.

    Args:
        external_session_id: External MCP client conversation/session id.
        objective: New research objective or user prompt.
        ui_summary: Optional compact UI summary.
        similarity_threshold: Reuse threshold from 0.0 to 1.0. Defaults to 0.55.
        max_candidates: Number of search/list candidates to inspect. Defaults
            to 3, capped at 10.
    """
    try:
        external = external_session_id.strip()
        objective = objective.strip()
        if not external:
            raise ValueError("external_session_id is required")
        if not objective:
            raise ValueError("objective is required")
        similarity_threshold = max(0.0, min(float(similarity_threshold), 1.0))
        max_candidates = max(1, min(int(max_candidates), 10))

        existing = _find_session_by_external_id(external)
        if existing is not None:
            return _json_ok(
                action="reused",
                reason="external_id_match",
                external_session_id=external,
                ui_session_id=existing.session_id,
                title=existing.title,
                matched_session=existing.to_dict(),
                similarity_score=1.0,
            )

        svc = _get_mcp_session_service()
        candidates: dict[str, Any] = {}
        from src.session.search import get_shared_index

        for match in get_shared_index().search(" ".join([objective, ui_summary]).strip(), max_sessions=max_candidates):
            session = svc.store.get_session(match.session_id)
            if session is not None:
                candidates[session.session_id] = session
        for session in svc.list_sessions(limit=max_candidates):
            candidates.setdefault(session.session_id, session)

        scored = sorted(
            (
                (_session_similarity(session, objective, ui_summary), session)
                for session in candidates.values()
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        if scored:
            top_score, top_session = scored[0]
            if top_score >= similarity_threshold:
                _attach_external_session_alias(top_session, external)
                return _json_ok(
                    action="reused",
                    reason="similarity_match",
                    external_session_id=external,
                    ui_session_id=top_session.session_id,
                    title=top_session.title,
                    matched_session=top_session.to_dict(),
                    similarity_score=round(top_score, 4),
                    candidates=[
                        {"session_id": s.session_id, "title": s.title, "similarity_score": round(score, 4)}
                        for score, s in scored[:max_candidates]
                    ],
                )

        title = _generate_session_title(objective, ui_summary)
        session = _ensure_ui_session(
            external,
            title=title,
            config={"topic_key": _blank_to_none(ui_summary), "goal_source": "mcp"},
        )
        return _json_ok(
            action="created",
            external_session_id=external,
            ui_session_id=session.session_id,
            title=session.title,
            session=session.to_dict(),
            candidates=[
                {"session_id": s.session_id, "title": s.title, "similarity_score": round(score, 4)}
                for score, s in scored[:max_candidates]
            ],
        )
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


# ---------------------------------------------------------------------------
# Goal tools
# ---------------------------------------------------------------------------


@mcp.tool
def start_research_goal(
    session_id: str,
    objective: str,
    criteria: list[str] | None = None,
    ui_summary: str = "",
    protocol: str = "thesis_review",
    risk_tier: str = "research_general",
    token_budget: int | None = None,
    turn_budget: int | None = None,
    time_budget_seconds: int | None = None,
) -> str:
    """Create or replace the current finance research goal for a session.

    This is the MCP entry point for long-running, research-only finance tasks.
    It creates an auditable goal with checklist criteria and supersedes any
    previous current goal for the same session.

    Args:
        session_id: External conversation/session id owned by the MCP client.
        objective: Research-only objective, not a trade execution request.
        criteria: Optional checklist. Defaults to the MVP finance protocol.
        ui_summary: Optional compact label for UI surfaces.
        protocol: Research protocol name. Defaults to thesis_review.
        risk_tier: One of the supported non-execution risk tiers.
        token_budget: Optional token budget.
        turn_budget: Optional turn budget.
        time_budget_seconds: Optional wall-clock budget.
    """
    try:
        ui_session = _ensure_ui_session(
            session_id,
            title=_generate_session_title(objective, ui_summary),
            config={"goal_source": "mcp"},
        )
        clean_criteria = _clean_list(criteria) or _default_goal_criteria()
        goal = _get_goal_store().replace_goal(
            session_id=ui_session.session_id,
            objective=objective,
            criteria=clean_criteria,
            ui_summary=ui_summary,
            source="mcp",
            protocol=protocol,
            risk_tier=_risk_tier_from_text(risk_tier),
            token_budget=token_budget,
            turn_budget=turn_budget,
            time_budget_seconds=time_budget_seconds,
        )
        snapshot = _get_goal_store().get_goal_snapshot(goal.goal_id)
        _append_ui_message(
            ui_session.session_id,
            "system",
            f"MCP research goal started: {objective}",
            metadata={
                "source": "mcp",
                "event": "goal.started",
                "external_session_id": session_id.strip(),
                "goal_id": goal.goal_id,
            },
        )
        return _json_ok(
            external_session_id=session_id.strip(),
            ui_session_id=ui_session.session_id,
            snapshot=snapshot,
        )
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


@mcp.tool
def get_research_goal(session_id: str) -> str:
    """Return the current finance research goal snapshot for a session.

    Args:
        session_id: External conversation/session id owned by the MCP client.
    """
    try:
        ui_session = _ensure_ui_session(session_id)
        snapshot = _get_goal_store().get_current_snapshot(ui_session.session_id)
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")
    if snapshot is None:
        return _json_error("No current goal", error_type="not_found")
    return _json_ok(
        external_session_id=session_id.strip(),
        ui_session_id=ui_session.session_id,
        snapshot=snapshot,
    )


@mcp.tool
def add_goal_evidence(
    session_id: str,
    goal_id: str,
    expected_goal_id: str,
    text: str,
    criterion_id: str | None = None,
    claim_id: str | None = None,
    evidence_type: str = "evidence",
    tool_call_id: str | None = None,
    run_id: str | None = None,
    source_provider: str | None = None,
    source_type: str | None = None,
    source_uri: str | None = None,
    symbol_universe: list[str] | None = None,
    benchmark: list[str] | None = None,
    timeframe: str | None = None,
    method: str | None = None,
    assumptions: dict[str, Any] | None = None,
    artifact_path: str | None = None,
    artifact_hash: str | None = None,
    data_as_of: str | None = None,
    confidence: str | None = None,
    caveat: str | None = None,
    contradicts_claim_ids: list[str] | None = None,
) -> str:
    """Append traceable evidence to a finance research goal.

    Args:
        session_id: External conversation/session id.
        goal_id: Goal being mutated.
        expected_goal_id: Goal id captured before the tool/model turn started.
        text: Evidence note or result summary.
        criterion_id: Optional criterion this evidence satisfies.
        claim_id: Optional claim this evidence supports or contradicts.
        evidence_type: Evidence category, default evidence.
        tool_call_id: Source tool call id for traceability; it does not verify evidence by itself.
        run_id: Vibe-Trading run id. It verifies evidence only when the run directory exists.
        source_provider: Data/provider name such as yfinance, OKX, tushare.
        source_type: Source category such as market_data, document, backtest.
        source_uri: Optional source URL/path.
        symbol_universe: Symbols covered by the evidence.
        benchmark: Benchmark symbols covered by the evidence.
        timeframe: Market timeframe.
        method: Research method used.
        assumptions: Structured assumptions.
        artifact_path: Artifact path. It verifies evidence only when allowed by path policy and paired with a matching sha256 hash.
        artifact_hash: Required sha256 when artifact_path should verify evidence.
        data_as_of: ISO timestamp/date for data freshness.
        confidence: Optional confidence label.
        caveat: Optional limitation note.
        contradicts_claim_ids: Claim ids contradicted by this evidence.
    """
    try:
        from src.goal import EvidenceInput, StaleGoalError

        ui_session = _ensure_ui_session(session_id)
        evidence = _get_goal_store().append_evidence(
            session_id=ui_session.session_id,
            goal_id=goal_id.strip(),
            expected_goal_id=expected_goal_id.strip(),
            evidence=EvidenceInput(
                criterion_id=_blank_to_none(criterion_id),
                claim_id=_blank_to_none(claim_id),
                evidence_type=evidence_type,
                text=text,
                tool_call_id=_blank_to_none(tool_call_id),
                run_id=_blank_to_none(run_id),
                source_provider=_blank_to_none(source_provider),
                source_type=_blank_to_none(source_type),
                source_uri=_blank_to_none(source_uri),
                symbol_universe=_clean_list(symbol_universe),
                benchmark=_clean_list(benchmark),
                timeframe=_blank_to_none(timeframe),
                method=_blank_to_none(method),
                assumptions=assumptions or {},
                artifact_path=_blank_to_none(artifact_path),
                artifact_hash=_blank_to_none(artifact_hash),
                data_as_of=_blank_to_none(data_as_of),
                confidence=_blank_to_none(confidence),
                caveat=_blank_to_none(caveat),
                contradicts_claim_ids=_clean_list(contradicts_claim_ids),
            ),
        )
        snapshot = _get_goal_store().get_goal_snapshot(goal_id.strip())
        if snapshot is None:
            return _json_error("Goal snapshot could not be reloaded")
        from dataclasses import asdict

        _append_ui_message(
            ui_session.session_id,
            "tool",
            f"Evidence added: {text}",
            metadata={
                "source": "mcp",
                "event": "goal.evidence",
                "external_session_id": session_id.strip(),
                "goal_id": goal_id.strip(),
                "evidence_id": evidence.evidence_id,
            },
        )
        return _json_ok(
            external_session_id=session_id.strip(),
            ui_session_id=ui_session.session_id,
            evidence=asdict(evidence),
            snapshot=snapshot,
        )
    except StaleGoalError as exc:
        return _json_error(str(exc), error_type="stale_goal")
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


@mcp.tool
def update_research_goal_status(
    session_id: str,
    goal_id: str,
    expected_goal_id: str,
    status: str,
    audit: list[dict[str, Any]] | None = None,
    recap: str | None = None,
) -> str:
    """Update a finance research goal status after an audit.

    Use this to complete, cancel, block, pause, or otherwise move the current
    goal through its lifecycle. ``complete`` requires one audit row per
    required criterion and verified evidence for satisfied rows.

    Args:
        session_id: External conversation/session id.
        goal_id: Goal being mutated.
        expected_goal_id: Goal id captured before the tool/model turn started.
        status: Goal lifecycle status, e.g. complete, cancelled, blocked.
        audit: Optional list of criterion audit rows.
        recap: Optional concise status recap.
    """
    try:
        from src.goal import GoalStatus, StaleGoalError

        ui_session = _ensure_ui_session(session_id)
        updated = _get_goal_store().update_status(
            session_id=ui_session.session_id,
            goal_id=goal_id.strip(),
            expected_goal_id=expected_goal_id.strip(),
            status=GoalStatus(status),
            audit=_audit_rows_from_payload(audit),
            recap=_blank_to_none(recap),
        )
        snapshot = _get_goal_store().get_goal_snapshot(updated.goal_id)
        if snapshot is None:
            return _json_error("Goal snapshot could not be reloaded")
        _append_ui_message(
            ui_session.session_id,
            "system",
            f"MCP research goal status updated to {status}: {recap or ''}".strip(),
            metadata={
                "source": "mcp",
                "event": "goal.status",
                "external_session_id": session_id.strip(),
                "goal_id": goal_id.strip(),
                "status": status,
            },
        )
        return _json_ok(
            external_session_id=session_id.strip(),
            ui_session_id=ui_session.session_id,
            goal=snapshot["goal"],
            snapshot=snapshot,
        )
    except StaleGoalError as exc:
        return _json_error(str(exc), error_type="stale_goal")
    except ValueError as exc:
        return _json_error(str(exc), error_type="validation")


# ---------------------------------------------------------------------------
# Backtest tool
# ---------------------------------------------------------------------------


@mcp.tool
def backtest(run_dir: str) -> str:
    """Run a vectorized backtest using config.json and code/signal_engine.py.

    The run_dir must contain:
    - config.json: backtest configuration (source, codes, dates, etc.)
    - code/signal_engine.py: strategy signal generation code

    Supported data sources (set in config.json "source" field):
    - "yfinance": HK/US equities (free, no API key needed)
    - "okx": cryptocurrency (free, no API key needed)
    - "tushare": China A-shares (requires TUSHARE_TOKEN env var)
    - "akshare": A-shares, US, HK, futures, forex (free, no API key)
    - "ccxt": crypto from 100+ exchanges (free, no API key)
    - "auto": auto-detect based on symbol format (with fallback)

    Returns metrics (Sharpe, return, drawdown, etc.) and artifact paths.

    Args:
        run_dir: Path to the run directory containing config.json and code/.
    """
    from src.tools.backtest_tool import run_backtest

    return run_backtest(run_dir)


# ---------------------------------------------------------------------------
# Factor analysis tool
# ---------------------------------------------------------------------------


@mcp.tool
def factor_analysis(
    codes: list[str],
    factor_name: str,
    start_date: str,
    end_date: str,
    source: str = "auto",
    top_n: int = 10,
    bottom_n: int = 10,
) -> str:
    """Compute factor IC/IR analysis and layered backtest for a cross-section of stocks.

    Analyzes factor predictive power using Spearman rank IC, IR (IC/std),
    and top/bottom quintile return spreads.

    Args:
        codes: List of stock codes (e.g. ["000001.SZ", "600519.SH"]).
        factor_name: Factor column name in daily_basic data (e.g. "pe_ttm", "pb", "turnover_rate").
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        source: Data source ("tushare", "yfinance", "auto").
        top_n: Number of top-ranked stocks per period.
        bottom_n: Number of bottom-ranked stocks per period.
    """
    registry = _get_registry()
    return registry.execute(
        "factor_analysis",
        {
            "codes": codes,
            "factor_name": factor_name,
            "start_date": start_date,
            "end_date": end_date,
            "source": source,
            "top_n": top_n,
            "bottom_n": bottom_n,
        },
    )


# ---------------------------------------------------------------------------
# Options pricing tool
# ---------------------------------------------------------------------------


@mcp.tool
def analyze_options(
    spot: float,
    strike: float,
    expiry_days: int,
    risk_free_rate: float = 0.03,
    volatility: float = 0.25,
    option_type: str = "call",
) -> str:
    """Calculate Black-Scholes option price and Greeks (Delta, Gamma, Theta, Vega).

    Args:
        spot: Current underlying price.
        strike: Strike price.
        expiry_days: Days until expiration.
        risk_free_rate: Annual risk-free rate (default 0.03 = 3%).
        volatility: Annual volatility (default 0.25 = 25%).
        option_type: "call" or "put".
    """
    registry = _get_registry()
    return registry.execute(
        "options_pricing",
        {
            "spot": spot,
            "strike": strike,
            "expiry_days": expiry_days,
            "risk_free_rate": risk_free_rate,
            "volatility": volatility,
            "option_type": option_type,
        },
    )


# ---------------------------------------------------------------------------
# Pattern recognition tool
# ---------------------------------------------------------------------------


@mcp.tool
def pattern_recognition(run_dir: str) -> str:
    """Detect technical chart patterns (head-and-shoulders, double top/bottom,
    triangles, wedges, channels) in OHLCV data.

    Reads price data from run_dir/artifacts/ohlcv_*.csv files.
    Can be called before coding (to inform strategy) or after backtest (to analyse).

    Args:
        run_dir: Path to run directory containing artifacts/ohlcv_*.csv.
    """
    registry = _get_registry()
    return registry.execute("pattern", {"run_dir": run_dir})


# ---------------------------------------------------------------------------
# Web & document reading tools
# ---------------------------------------------------------------------------


@mcp.tool
def read_url(url: str) -> str:
    """Fetch a web page and convert it to clean Markdown text.

    Strips ads, navigation, and styling. Useful for reading API docs,
    financial articles, research reports, and GitHub READMEs.

    Args:
        url: Target URL to read.
    """
    from src.tools.web_reader_tool import read_url as _read_url

    return _read_url(url)


@mcp.tool
def read_document(file_path: str) -> str:
    """Extract text from a PDF document with OCR fallback for scanned pages.

    Supports text-based and image-based PDFs. Automatically uses OCR
    for pages with insufficient extractable text.

    Args:
        file_path: Absolute path to the PDF file.
    """
    registry = _get_registry()
    return registry.execute("read_document", {"file_path": file_path})


# ---------------------------------------------------------------------------
# Web search tool
# ---------------------------------------------------------------------------


@mcp.tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo and return top results.

    Returns titles, URLs, and snippets. Use read_url() to fetch full content
    from any result URL. Free, no API key required.

    Args:
        query: Search query string.
        max_results: Maximum results to return (default 5, max 10).
    """
    registry = _get_registry()
    return registry.execute(
        "web_search",
        {
            "query": query,
            "max_results": min(max_results, 10),
        },
    )


# ---------------------------------------------------------------------------
# File I/O tools (sandboxed to workspace)
# ---------------------------------------------------------------------------


@mcp.tool
def write_file(path: str, content: str) -> str:
    """Write content to a file. Used to create config.json and signal_engine.py
    for backtesting workflows.

    Args:
        path: File path (relative to workspace or absolute).
        content: File content to write.
    """
    registry = _get_registry()
    return registry.execute("write_file", {"path": path, "content": content})


@mcp.tool
def read_file(path: str) -> str:
    """Read the contents of a file.

    Args:
        path: File path to read.
    """
    registry = _get_registry()
    return registry.execute("read_file", {"path": path})


# ---------------------------------------------------------------------------
# Trading connector tools
# ---------------------------------------------------------------------------


def _trading_common_args(
    *,
    connection: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    account: str | None = None,
) -> dict[str, Any]:
    """Build shared optional trading connector arguments."""
    payload: dict[str, Any] = {}
    if connection:
        payload["connection"] = connection
    if host:
        payload["host"] = host
    if port is not None:
        payload["port"] = port
    if client_id is not None:
        payload["client_id"] = client_id
    if account:
        payload["account"] = account
    return payload


@mcp.tool
def trading_connections() -> str:
    """List selectable trading connector profiles.

    The connector is the first-level choice. Paper/live is an attribute of each
    profile under that connector.
    """
    registry = _get_registry()
    return registry.execute("trading_connections", {})


@mcp.tool
def trading_select_connection(connection: str) -> str:
    """Select the default trading connector profile for later trading_* calls.

    Args:
        connection: Profile id, e.g. ``ibkr-paper-local`` or ``robinhood-live-mcp``.
    """
    registry = _get_registry()
    return registry.execute("trading_select_connection", {"connection": connection})


@mcp.tool
def trading_check(
    connection: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    account: str | None = None,
) -> str:
    """Check whether a trading connector profile is configured and reachable.

    This never places orders. For local profiles, it checks the user's local
    app/socket. For remote MCP profiles, it reports config and OAuth-token
    presence without returning secrets.

    Args:
        connection: Optional profile id. Defaults to the selected profile.
        host: Optional local host override.
        port: Optional local socket port override.
        client_id: Optional local client id override.
        account: Optional account code filter.
    """
    registry = _get_registry()
    return registry.execute(
        "trading_check",
        _trading_common_args(connection=connection, host=host, port=port, client_id=client_id, account=account),
    )


@mcp.tool
def trading_account(
    connection: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    account: str | None = None,
) -> str:
    """Read account data from the selected trading connector profile.

    Args:
        connection: Optional profile id. Defaults to the selected profile.
        host: Optional local host override.
        port: Optional local socket port override.
        client_id: Optional local client id override.
        account: Optional account code filter.
    """
    registry = _get_registry()
    return registry.execute(
        "trading_account",
        _trading_common_args(connection=connection, host=host, port=port, client_id=client_id, account=account),
    )


@mcp.tool
def trading_positions(
    connection: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    account: str | None = None,
) -> str:
    """Read positions from the selected trading connector profile.

    Args:
        connection: Optional profile id. Defaults to the selected profile.
        host: Optional local host override.
        port: Optional local socket port override.
        client_id: Optional local client id override.
        account: Optional account code filter.
    """
    registry = _get_registry()
    return registry.execute(
        "trading_positions",
        _trading_common_args(connection=connection, host=host, port=port, client_id=client_id, account=account),
    )


@mcp.tool
def trading_orders(
    connection: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    account: str | None = None,
    include_executions: bool = False,
) -> str:
    """Read open orders from the selected trading connector profile.

    Read-only: this tool does not place, cancel, modify, or replace orders.

    Args:
        connection: Optional profile id. Defaults to the selected profile.
        host: Optional local host override.
        port: Optional local socket port override.
        client_id: Optional local client id override.
        account: Optional account code filter.
        include_executions: Include recent executions when available.
    """
    params = _trading_common_args(connection=connection, host=host, port=port, client_id=client_id, account=account)
    params["include_executions"] = include_executions
    registry = _get_registry()
    return registry.execute("trading_orders", params)


@mcp.tool
def trading_quote(
    symbol: str,
    connection: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    account: str | None = None,
    exchange: str = "SMART",
    currency: str = "USD",
    sec_type: str = "STK",
) -> str:
    """Read a quote snapshot from the selected trading connector profile.

    Args:
        symbol: Symbol such as AAPL.
        connection: Optional profile id. Defaults to the selected profile.
        host: Optional local host override.
        port: Optional local socket port override.
        client_id: Optional local client id override.
        account: Optional account code filter.
        exchange: Exchange routing, default SMART.
        currency: Contract currency, default USD.
        sec_type: Security type, default STK.
    """
    params = _trading_common_args(connection=connection, host=host, port=port, client_id=client_id, account=account)
    params.update({"symbol": symbol, "exchange": exchange, "currency": currency, "sec_type": sec_type})
    registry = _get_registry()
    return registry.execute("trading_quote", params)


@mcp.tool
def trading_history(
    symbol: str,
    connection: str | None = None,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    account: str | None = None,
    exchange: str = "SMART",
    currency: str = "USD",
    sec_type: str = "STK",
    duration: str = "30 D",
    bar_size: str = "1 day",
    what_to_show: str = "TRADES",
    use_rth: bool = True,
) -> str:
    """Read historical bars from the selected trading connector profile.

    Args:
        symbol: Symbol such as AAPL.
        connection: Optional profile id. Defaults to the selected profile.
        host: Optional local host override.
        port: Optional local socket port override.
        client_id: Optional local client id override.
        account: Optional account code filter.
        exchange: Exchange routing, default SMART.
        currency: Contract currency, default USD.
        sec_type: Security type, default STK.
        duration: IBKR duration string, default 30 D.
        bar_size: IBKR bar size, default 1 day.
        what_to_show: Data type, default TRADES.
        use_rth: Use regular trading hours.
    """
    params = _trading_common_args(connection=connection, host=host, port=port, client_id=client_id, account=account)
    params.update(
        {
            "symbol": symbol,
            "exchange": exchange,
            "currency": currency,
            "sec_type": sec_type,
            "duration": duration,
            "bar_size": bar_size,
            "what_to_show": what_to_show,
            "use_rth": use_rth,
        }
    )
    registry = _get_registry()
    return registry.execute("trading_history", params)


# ---------------------------------------------------------------------------
# Swarm team tool
# ---------------------------------------------------------------------------


@mcp.tool
def list_swarm_presets() -> str:
    """List available swarm multi-agent team presets.

    Each preset defines a team of specialized agents (e.g. investment committee,
    quant desk, risk committee) that collaborate on complex research tasks.
    Returns preset names, descriptions, agent counts, and required variables.
    """
    from src.swarm.presets import list_presets

    presets = list_presets()
    return json.dumps(presets, ensure_ascii=False, indent=2)


@mcp.tool
async def run_swarm(
    preset_name: str,
    variables: dict[str, str],
    wait_seconds: int = 3600,
    start_only: bool = False,
    ctx: Context | None = None,
) -> str:
    """Run a swarm multi-agent team and stream progress back to the caller.

    Assembles a team of specialized agents that collaborate through a DAG workflow.
    For example, the 'investment_committee' preset runs bull analyst, bear analyst,
    risk officer, and portfolio manager in sequence.

    Use list_swarm_presets() to see available presets and their required variables.

    The tool keeps the MCP call open via ``Context.report_progress`` while the
    swarm runs, so the caller sees live "N/M tasks complete" updates instead
    of timing out silently. Only if ``wait_seconds`` is exhausted does the
    tool return early with the current ``run_id`` — call ``get_run_result``
    afterwards to fetch the final report.

    Args:
        preset_name: Swarm preset name (e.g. 'investment_committee', 'quant_strategy_desk').
        variables: Required variables for the preset (e.g. {"target": "AAPL.US", "market": "US"}).
        wait_seconds: Maximum seconds to keep the MCP call open. Default 3600
            (1 hour); the progress-notification keepalive means the transport
            stays connected for the full budget.
        start_only: If True, kick off the run and return immediately with
            ``run_id`` + current status. Ignores ``wait_seconds``.
    """
    import asyncio
    import time
    from src.config import load_swarm_agent_config
    from src.swarm.runtime import SwarmRuntime
    from src.swarm.store import SwarmStore, swarm_runs_root

    swarm_dir = swarm_runs_root()
    store = SwarmStore(base_dir=swarm_dir)
    # Boot-time / operator-trusted: resolved from env var or on-disk config.
    # The MCP caller (this tool's invoker) cannot influence the path — the
    # ``variables`` arg below is template data, never config (R-06).
    agent_config = load_swarm_agent_config()
    runtime = SwarmRuntime(store=store, agent_config=agent_config)

    try:
        run = runtime.start_run(
            preset_name, variables, include_shell_tools=_include_shell_tools
        )
    except FileNotFoundError as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"status": "error", "error": f"DAG validation failed: {exc}"}, ensure_ascii=False)

    if start_only or wait_seconds <= 0:
        return json.dumps(
            _build_run_payload(store, run.id, preset_name, timed_out=False),
            ensure_ascii=False,
            indent=2,
        )

    # Surface the run_id immediately in a fixed-format progress message so a
    # caller whose transport drops mid-run (or whose MCP client enforces a
    # hard tool-call timeout that ignores progress notifications) can still
    # recover the run via ``get_run_result(run_id)``. Parsers should match
    # ``swarm_started run_id=<id>`` literally; later frames are free-form.
    if ctx is not None:
        try:
            await ctx.report_progress(
                progress=0,
                total=1,
                message=f"swarm_started run_id={run.id} preset={preset_name}",
            )
        except Exception:
            pass

    terminal = {"completed", "failed", "cancelled"}
    started_at = time.monotonic()
    deadline = started_at + wait_seconds
    while True:
        payload = _build_run_payload(store, run.id, preset_name, timed_out=False)
        if payload["status"] == "error":
            return json.dumps(payload, ensure_ascii=False)
        if payload["status"] in terminal:
            return json.dumps(payload, ensure_ascii=False, indent=2)

        # Emit a progress frame every loop, NOT only on state change — MCP
        # clients use these as transport keepalive. A long task that doesn't
        # transition for 30 minutes still needs ticks or the client times out.
        # ``elapsed`` keeps the message content fresh so dedup-on-message
        # clients still see updates.
        if ctx is not None:
            tasks = payload.get("tasks") or []
            total = max(1, len(tasks))
            done = sum(1 for t in tasks if t.get("status") in terminal)
            elapsed = int(time.monotonic() - started_at)
            try:
                await ctx.report_progress(
                    progress=done,
                    total=total,
                    message=f"{done}/{total} tasks complete · {elapsed}s elapsed (run {run.id})",
                )
            except Exception:
                pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            payload = _build_run_payload(store, run.id, preset_name, timed_out=True)
            return json.dumps(payload, ensure_ascii=False, indent=2)
        await asyncio.sleep(min(5.0, remaining))


# ---------------------------------------------------------------------------
# Market data tool
# ---------------------------------------------------------------------------

def _detect_source(code: str) -> str:
    return detect_source(code)


def _get_loader(source: str):
    """Get loader class via registry with fallback support."""
    return get_loader(source)


def _cap_rows(records: list, max_rows: int) -> list | dict[str, object]:
    """Bound a per-symbol row list to keep the MCP payload within budget.

    max_rows==0 disables the cap (full list, unchanged shape). A negative
    max_rows is invalid and enforces the default cap (never unbounded).
    Otherwise an oversized symbol is *evenly strided* — every step-th bar,
    with the last bar pinned — so the returned series spans the full range
    (no head+tail gap, no synthetic ``_gap`` sentinel). Symbols within the
    cap are returned unchanged (plain list) — small queries are
    byte-identical.
    """
    return cap_rows(records, max_rows)


@mcp.tool
def get_market_data(
    codes: list[str],
    start_date: str,
    end_date: str,
    source: str = "auto",
    interval: str = "1D",
    max_rows: int = DEFAULT_MAX_ROWS,
) -> str:
    """Fetch OHLCV market data for stocks, crypto, or mixed symbols.

    Supported sources:
    - "yfinance": HK/US equities (free, e.g. AAPL.US, 700.HK)
    - "okx": cryptocurrency (free, e.g. BTC-USDT, ETH-USDT)
    - "tushare": China A-shares (requires TUSHARE_TOKEN, e.g. 000001.SZ)
    - "baostock": China A-shares via TCP protocol, bypasses HTTP CDN blocks (e.g. 000001.SZ, 601595.SH)
    - "tencent": China A-shares via Tencent Finance API (e.g. 000001.SZ, 601595.SH)
    - "akshare": A-shares, US, HK, futures, forex (free, e.g. 000001.SZ, AAPL.US)
    - "ccxt": crypto from 100+ exchanges (free, e.g. BTC/USDT)
    - "auto": auto-detect based on symbol format (with fallback)

    Args:
        codes: List of symbols (e.g. ["AAPL.US", "BTC-USDT", "000001.SZ"]).
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        source: Data source ("auto", "yfinance", "okx", "tushare", "baostock", "tencent", "akshare", "ccxt").
        interval: Bar size (1m/5m/15m/30m/1H/4H/1D, default "1D").
        max_rows: Per-symbol row cap (default 250) so the response stays
            within the MCP token budget. A symbol exceeding it returns an
            even-stride downsample (every step-th bar, last bar pinned)
            plus truncation metadata. Set max_rows=0 for all rows
            (unbounded, legacy behavior).
    """
    return fetch_market_data_json(
        codes=codes,
        start_date=start_date,
        end_date=end_date,
        source=source,
        interval=interval,
        max_rows=max_rows,
        loader_resolver=_get_loader,
    )


# ---------------------------------------------------------------------------
# Swarm status & history tools
# ---------------------------------------------------------------------------


def _get_swarm_store():
    from src.swarm.store import SwarmStore, swarm_runs_root

    swarm_dir = swarm_runs_root()
    swarm_dir.mkdir(parents=True, exist_ok=True)
    return SwarmStore(base_dir=swarm_dir)


def _run_to_dict(run, *, timed_out: bool = False, is_stale: bool = False) -> dict:
    """Public projection of a (live-hydrated) :class:`SwarmRun`.

    ``timed_out`` flips on only for the ``run_swarm`` wait-budget path. It does
    not change the run's actual status — callers can still see ``running`` and
    fetch the final report later via :func:`get_run_result`.

    ``is_stale`` is a read-only signal: ``True`` means the run is still
    ``running`` but its events.jsonl has been silent past the per-run
    threshold. No disk state is changed by setting this — the explicit
    :func:`reap_stale_runs` tool is what finalizes a stale run.
    """
    from src.swarm.serialization import run_level_error, serialize_task

    return {
        "run_id": run.id,
        "status": run.status.value,
        "preset": run.preset_name,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "error": run_level_error(run),
        "tasks": [serialize_task(t) for t in run.tasks],
        "final_report": run.final_report,
        "total_input_tokens": run.total_input_tokens,
        "total_output_tokens": run.total_output_tokens,
        "timed_out": timed_out,
        "is_stale": is_stale,
    }


def _build_run_payload(store, run_id: str, preset_name: str | None, *, timed_out: bool) -> dict:
    """Reconcile + project a run for the MCP response.

    Used by ``run_swarm`` (polling + start_only). Returns a normal payload on
    success and a ``{"status": "error", ...}`` envelope when the run record
    disappears (mid-run directory wipe / sandbox eviction).
    """
    run = store.load_run(run_id)
    if run is None:
        return {"status": "error", "error": "Run record lost", "run_id": run_id}
    reconciled = store.reconcile_run(run, write=True)
    payload = _run_to_dict(
        reconciled,
        timed_out=timed_out,
        is_stale=store.is_run_stale(reconciled),
    )
    if preset_name:
        payload["preset"] = preset_name
    return payload


@mcp.tool
def get_swarm_status(run_id: str) -> str:
    """Get the current status of a swarm run.

    Returns status, task progress, token usage, and an ``is_stale`` flag for
    the specified run. Use this to poll a long-running swarm without blocking.

    Args:
        run_id: The run ID returned by run_swarm.
    """
    store = _get_swarm_store()
    run = store.load_run(run_id)
    if run is None:
        return json.dumps({"status": "error", "error": f"Run {run_id} not found"}, ensure_ascii=False)
    reconciled = store.reconcile_run(run, write=True)
    return json.dumps(
        _run_to_dict(reconciled, is_stale=store.is_run_stale(reconciled)),
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool
def get_run_result(run_id: str) -> str:
    """Get the final report and task summaries of a swarm run.

    Reconciles the run on read: an orphaned ``running`` run whose host
    process exited will be transitioned to its real terminal status
    (``completed`` / ``failed`` / ``cancelled`` derived from the task
    statuses), so the caller never sees a permanent zombie.

    Args:
        run_id: The run ID returned by run_swarm.
    """
    store = _get_swarm_store()
    run = store.load_run(run_id)
    if run is None:
        return json.dumps({"status": "error", "error": f"Run {run_id} not found"}, ensure_ascii=False)
    reconciled = store.reconcile_run(run, write=True)
    payload = _run_to_dict(reconciled, is_stale=store.is_run_stale(reconciled))
    payload["ready"] = payload["status"] in {"completed", "failed", "cancelled"}
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool
def list_runs(limit: int = 20) -> str:
    """List recent swarm runs sorted by creation time (newest first).

    Each row includes task counts and an ``is_stale`` flag so callers can
    spot abandoned runs without a follow-up status call.

    Args:
        limit: Maximum number of runs to return (default 20).
    """
    store = _get_swarm_store()
    runs = store.list_runs(limit=limit)
    items = []
    for run in runs:
        # write=True so a zombie listed alongside live runs gets finalized;
        # the cost is bounded by ``limit`` (default 20) and most rows are
        # already terminal — reconcile is a no-op for those.
        reconciled = store.reconcile_run(run, write=True)
        counts = {"total": len(reconciled.tasks)}
        for t in reconciled.tasks:
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        items.append(
            {
                "run_id": reconciled.id,
                "preset": reconciled.preset_name,
                "status": reconciled.status.value,
                "is_stale": store.is_run_stale(reconciled),
                "created_at": reconciled.created_at,
                "completed_at": reconciled.completed_at,
                "task_counts": counts,
                "total_input_tokens": reconciled.total_input_tokens,
                "total_output_tokens": reconciled.total_output_tokens,
            }
        )
    return json.dumps(items, ensure_ascii=False, indent=2)


@mcp.tool
def reap_stale_runs() -> str:
    """Mark every ``running`` run whose host process died as ``failed``.

    Walks the swarm store, applies the per-run stale threshold, and
    finalizes any run that has gone silent past it (writes ``run.json`` +
    ``tasks/*.json`` + appends a ``run_reaped`` event). Already-terminal
    runs and still-alive runs are left untouched.

    Returns:
        JSON list of reaped run IDs (empty when nothing was stale).
    """
    store = _get_swarm_store()
    reaped = store.reap_stale_running_runs()
    return json.dumps({"reaped": reaped}, ensure_ascii=False, indent=2)


@mcp.tool
def retry_run(run_id: str) -> str:
    """Retry a failed, stale, or cancelled swarm run.

    Re-launches a brand-new run with the same preset and variables as the
    original; the original run is left untouched as a record. Use this after
    spotting a ``failed`` or stale run via ``list_runs``. A still-``running``
    run cannot be retried — cancel or reap it first.

    Args:
        run_id: ID of the run to retry (from ``list_runs`` / ``get_swarm_status``).

    Returns:
        JSON payload for the newly created run (``run_id`` / ``status`` /
        ``preset`` …), or an ``error`` object if the run is missing or active.
    """
    from src.config import load_swarm_agent_config
    from src.swarm.models import RunStatus
    from src.swarm.runtime import SwarmRuntime

    store = _get_swarm_store()
    loaded = store.load_run(run_id)
    if loaded is None:
        return json.dumps({"status": "error", "error": f"Run {run_id} not found"}, ensure_ascii=False)

    # Reconcile first so a zombie "running" run whose host died is demoted
    # before we gate on status; only a genuinely active run blocks retry.
    reconciled = store.reconcile_run(loaded, write=True)
    if reconciled.status == RunStatus.running:
        return json.dumps(
            {"status": "error", "error": "Cannot retry a running run. Cancel or reap it first."},
            ensure_ascii=False,
        )

    agent_config = load_swarm_agent_config()
    runtime = SwarmRuntime(store=store, agent_config=agent_config)
    try:
        new_run = runtime.start_run(
            reconciled.preset_name,
            reconciled.user_vars or {},
            include_shell_tools=_include_shell_tools,
        )
    except FileNotFoundError as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
    except ValueError as exc:
        return json.dumps({"status": "error", "error": f"DAG validation failed: {exc}"}, ensure_ascii=False)

    return json.dumps(
        _build_run_payload(store, new_run.id, new_run.preset_name, timed_out=False),
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Trade journal tool
# ---------------------------------------------------------------------------


@mcp.tool
def analyze_trade_journal(
    file_path: str,
    analysis_type: str = "full",
    filter_expr: str = "",
) -> str:
    """Analyze a user's trade journal (CSV/Excel broker export) and return
    a trading profile plus behavior diagnostics.

    Parses 同花顺 / 东方财富 / 富途 / generic formats (encoding auto-detected).
    Output (JSON):
      - profile: holding days, frequency, win rate, PnL ratio, top symbols,
                 market distribution, hourly distribution
      - behaviors: disposition effect, overtrading, chasing momentum,
                   anchoring (each with severity + numeric evidence)

    Args:
        file_path: Absolute path to the uploaded CSV/Excel file.
        analysis_type: "full" | "profile" | "behavior" | "strategy".
        filter_expr: Optional filter (e.g. "2026-01 to 2026-03",
                     "symbol=600519.SH", "market=china_a").
    """
    registry = _get_registry()
    return registry.execute(
        "analyze_trade_journal",
        {
            "file_path": file_path,
            "analysis_type": analysis_type,
            "filter_expr": filter_expr,
        },
    )


# ---------------------------------------------------------------------------
# Shadow Account tools (4)
# ---------------------------------------------------------------------------


@mcp.tool
def extract_shadow_strategy(
    journal_path: str,
    min_support: int = 3,
    max_rules: int = 5,
) -> str:
    """Extract a Shadow Account profile (3-5 human-readable if-then rules)
    from the user's profitable roundtrips in a trade journal.

    Run `analyze_trade_journal` first if the journal hasn't been parsed.
    Returns shadow_id + rules preview. Profile persists to
    ~/.vibe-trading/shadow_accounts/.

    Args:
        journal_path: Path to the CSV/Excel broker export.
        min_support: Minimum profitable roundtrips required to back one rule.
        max_rules: Maximum rules to return (typically 3-5).
    """
    registry = _get_registry()
    return registry.execute(
        "extract_shadow_strategy",
        {
            "journal_path": journal_path,
            "min_support": min_support,
            "max_rules": max_rules,
        },
    )


@mcp.tool
def run_shadow_backtest(
    shadow_id: str,
    window_start: str = "",
    window_end: str = "",
    markets: list[str] | None = None,
    journal_path: str = "",
) -> str:
    """Run a multi-market backtest (A股/港股/美股/crypto) on a Shadow Account
    profile and compute delta-PnL attribution vs the user's realized trades.

    Requires `extract_shadow_strategy` to have run first.

    Args:
        shadow_id: ID returned by extract_shadow_strategy.
        window_start: ISO date, default today-1y.
        window_end: ISO date, default today.
        markets: Subset of ["china_a", "hk", "us", "crypto"], default all four.
        journal_path: Original journal path (enables attribution), optional.
    """
    registry = _get_registry()
    params: dict[str, Any] = {"shadow_id": shadow_id}
    if window_start:
        params["window_start"] = window_start
    if window_end:
        params["window_end"] = window_end
    if markets:
        params["markets"] = markets
    if journal_path:
        params["journal_path"] = journal_path
    return registry.execute("run_shadow_backtest", params)


@mcp.tool
def render_shadow_report(
    shadow_id: str,
    include_today_signals: bool = True,
    window_start: str = "",
    window_end: str = "",
    journal_path: str = "",
) -> str:
    """Render the Shadow Account HTML/PDF report (8 sections + charts) for
    a shadow_id. If no cached backtest, one is run automatically.

    Args:
        shadow_id: Shadow Account ID.
        include_today_signals: Include today's market scan section.
        window_start: Optional backtest window override.
        window_end: Optional backtest window override.
        journal_path: Original journal path (for attribution), optional.
    """
    registry = _get_registry()
    params: dict[str, Any] = {
        "shadow_id": shadow_id,
        "include_today_signals": include_today_signals,
    }
    if window_start:
        params["window_start"] = window_start
    if window_end:
        params["window_end"] = window_end
    if journal_path:
        params["journal_path"] = journal_path
    return registry.execute("render_shadow_report", params)


@mcp.tool
def scan_shadow_signals(
    shadow_id: str,
    date: str = "",
    per_market: int = 3,
) -> str:
    """List today's symbols that match the Shadow Account's entry cadence
    (research use only — not a trade recommendation).

    Args:
        shadow_id: Shadow Account ID.
        date: ISO YYYY-MM-DD target date, default today.
        per_market: Max signals per market.
    """
    registry = _get_registry()
    params: dict[str, Any] = {"shadow_id": shadow_id, "per_market": per_market}
    if date:
        params["date"] = date
    return registry.execute("scan_shadow_signals", params)


# ---------------------------------------------------------------------------
# Investment Workspace / Portfolio MCP tools
# ---------------------------------------------------------------------------

PORTFOLIO_ENTITIES = {
    "account": "PortfolioAccount",
    "instrument": "Instrument",
    "watchlist": "WatchlistItem",
    "position": "Position",
    "lot": "PositionLot",
    "price": "PriceSnapshot",
    "research": "ResearchReport",
    "rule": "TrackingRule",
    "rule_event": "RuleTriggerEvent",
    "decision": "DecisionLog",
    "import_job": "PositionImportJob",
    "import_item": "PositionImportItem",
}


def _portfolio_session_scope():
    from src.portfolio.db import session_scope

    return session_scope()


def _portfolio_model(entity: str):
    from src.portfolio import models as pm

    key = entity.strip().lower()
    if key not in PORTFOLIO_ENTITIES:
        raise ValueError(f"unsupported portfolio entity: {entity}; allowed: {', '.join(sorted(PORTFOLIO_ENTITIES))}")
    return getattr(pm, PORTFOLIO_ENTITIES[key])


def _portfolio_dump(value: Any) -> Any:
    from datetime import date, datetime

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_portfolio_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _portfolio_dump(item) for key, item in value.items() if not str(key).startswith("_sa_")}
    if hasattr(value, "__table__"):
        data = {column.name: _portfolio_dump(getattr(value, column.name)) for column in value.__table__.columns}
        for rel in getattr(value, "__mapper__").relationships:
            if rel.key in value.__dict__:
                data[rel.key] = _portfolio_dump(getattr(value, rel.key))
        return data
    return str(value)


def _portfolio_parse_datetime(value: Any):
    from datetime import datetime

    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return value


def _portfolio_clean_data(model: Any, data: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    columns = {column.name: column for column in model.__table__.columns}
    blocked = {"id", "created_at", "updated_at"}
    cleaned: dict[str, Any] = {}
    for key, value in (data or {}).items():
        if key in blocked or key not in columns:
            continue
        column = columns[key]
        if column.type.__class__.__name__ == "DateTime":
            value = _portfolio_parse_datetime(value)
        cleaned[key] = value
    if not partial and model.__name__ == "Instrument":
        if "symbol" in cleaned and isinstance(cleaned["symbol"], str):
            cleaned["symbol"] = cleaned["symbol"].upper()
        if "market" in cleaned and isinstance(cleaned["market"], str):
            cleaned["market"] = cleaned["market"].upper()
    return cleaned


@mcp.tool
def portfolio_health() -> str:
    """Check whether the Investment Workspace database is reachable.

    Returns database connection status for PostgreSQL-backed portfolio data.
    """
    try:
        with _portfolio_session_scope():
            pass
        return _json_ok(database="connected")
    except Exception as exc:
        return _json_error(str(exc), error_type="database")


@mcp.tool
def portfolio_dashboard() -> str:
    """Return Investment Workspace dashboard totals and recent reports."""
    try:
        from src.portfolio import service as ps

        with _portfolio_session_scope() as session:
            return _json_ok(dashboard=_portfolio_dump(ps.dashboard(session)))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_list_records(entity: str, limit: int = 100, filters: dict[str, Any] | None = None) -> str:
    """List Investment Workspace records for any supported entity.

    Args:
        entity: One of account, instrument, watchlist, position, lot, price,
            research, rule, rule_event, decision, import_job, import_item.
        limit: Maximum records to return, capped at 500.
        filters: Exact-match filters by column name, e.g. {"symbol": "AAPL"}.
    """
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        model = _portfolio_model(entity)
        limit = max(1, min(int(limit), 500))
        with _portfolio_session_scope() as session:
            stmt = select(model).limit(limit)
            for key, value in (filters or {}).items():
                if hasattr(model, key):
                    stmt = stmt.where(getattr(model, key) == value)
            if entity.strip().lower() == "position":
                from src.portfolio import models as pm

                stmt = stmt.options(joinedload(pm.Position.instrument), joinedload(pm.Position.account))
            records = list(session.execute(stmt).unique().scalars())
            if entity.strip().lower() == "position":
                from src.portfolio import service as ps

                data = [{**_portfolio_dump(record), **ps.position_metrics(session, record)} for record in records]
            else:
                data = _portfolio_dump(records)
            return _json_ok(entity=entity, count=len(records), records=data)
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_get_record(entity: str, record_id: str) -> str:
    """Get one Investment Workspace record by entity and id."""
    try:
        model = _portfolio_model(entity)
        with _portfolio_session_scope() as session:
            record = session.get(model, record_id)
            if record is None:
                return _json_error("record not found", error_type="not_found")
            return _json_ok(entity=entity, record=_portfolio_dump(record))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_create_record(entity: str, data: dict[str, Any]) -> str:
    """Create one Investment Workspace record for any supported entity.

    Args:
        entity: Supported portfolio entity name.
        data: Column data. id/created_at/updated_at are ignored.
    """
    try:
        from src.portfolio import service as ps
        from src.portfolio import schemas as psc

        entity_key = entity.strip().lower()
        with _portfolio_session_scope() as session:
            if entity_key == "position":
                record = ps.create_position(session, psc.PositionCreate(**data))
            elif entity_key == "lot":
                record, _ = ps.add_position_lot(session, psc.PositionLotCreate(**data))
            elif entity_key == "price":
                record = ps.add_price_snapshot(session, psc.PriceSnapshotCreate(**data))
            else:
                model = _portfolio_model(entity_key)
                record = model(**_portfolio_clean_data(model, data))
                session.add(record)
                session.flush()
            return _json_ok(entity=entity_key, record=_portfolio_dump(record))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_update_record(entity: str, record_id: str, data: dict[str, Any]) -> str:
    """Update one Investment Workspace record by entity and id.

    Args:
        entity: Supported portfolio entity name.
        record_id: Record id.
        data: Partial column data. id/created_at/updated_at are ignored.
    """
    try:
        model = _portfolio_model(entity)
        with _portfolio_session_scope() as session:
            record = session.get(model, record_id)
            if record is None:
                return _json_error("record not found", error_type="not_found")
            for key, value in _portfolio_clean_data(model, data, partial=True).items():
                setattr(record, key, value)
            session.flush()
            return _json_ok(entity=entity, record=_portfolio_dump(record))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_delete_record(entity: str, record_id: str, soft_delete: bool = True) -> str:
    """Delete or archive one Investment Workspace record.

    For instruments and accounts, soft_delete=true marks is_active=false when
    that column exists. Other records are physically deleted.
    """
    try:
        model = _portfolio_model(entity)
        with _portfolio_session_scope() as session:
            record = session.get(model, record_id)
            if record is None:
                return _json_error("record not found", error_type="not_found")
            if soft_delete and hasattr(record, "is_active"):
                record.is_active = False
            else:
                session.delete(record)
            session.flush()
            return _json_ok(entity=entity, id=record_id)
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_upsert_instrument(
    symbol: str,
    name: str,
    market: str = "US",
    asset_class: str = "equity",
    currency: str = "USD",
    sector: str = "",
    region: str = "",
    tags: list[str] | None = None,
    thesis: str = "",
    data_source: str = "",
) -> str:
    """Create or update an investment instrument tracked by the workspace."""
    try:
        from src.portfolio import service as ps
        from src.portfolio import schemas as psc

        with _portfolio_session_scope() as session:
            instrument = ps.find_instrument(session, symbol, market)
            payload = {
                "symbol": symbol,
                "name": name,
                "market": market,
                "asset_class": asset_class,
                "currency": currency,
                "sector": _blank_to_none(sector),
                "region": _blank_to_none(region),
                "tags": tags or [],
                "thesis": _blank_to_none(thesis),
                "data_source": _blank_to_none(data_source),
            }
            if instrument:
                instrument = ps.update_instrument(session, instrument.id, psc.InstrumentUpdate(**payload))
                action = "updated"
            else:
                instrument = ps.create_instrument(session, psc.InstrumentCreate(**payload))
                action = "created"
            return _json_ok(action=action, instrument=_portfolio_dump(instrument))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_upsert_position(
    symbol: str,
    name: str,
    quantity: float,
    avg_cost: float,
    market: str = "US",
    asset_class: str = "equity",
    currency: str = "USD",
    account_name: str = "Default Manual Account",
    broker: str = "manual",
    target_weight: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    notes: str = "",
) -> str:
    """Create or update a holding position by symbol/account."""
    try:
        from sqlalchemy import select
        from src.portfolio import models as pm
        from src.portfolio import service as ps
        from src.portfolio import schemas as psc

        with _portfolio_session_scope() as session:
            instrument = ps.find_instrument(session, symbol, market)
            if not instrument:
                instrument = ps.create_instrument(
                    session,
                    psc.InstrumentCreate(symbol=symbol, name=name, market=market, asset_class=asset_class, currency=currency),
                )
            account = session.execute(select(pm.PortfolioAccount).where(pm.PortfolioAccount.name == account_name).limit(1)).scalar_one_or_none()
            if not account:
                account = pm.PortfolioAccount(name=account_name, broker=broker, account_type="manual", base_currency=currency)
                session.add(account)
                session.flush()
            position = session.execute(
                select(pm.Position).where(pm.Position.account_id == account.id, pm.Position.instrument_id == instrument.id).limit(1)
            ).scalar_one_or_none()
            payload = {
                "quantity": quantity,
                "avg_cost": avg_cost,
                "cost_basis": quantity * avg_cost,
                "target_weight": target_weight,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "notes": _blank_to_none(notes),
            }
            if position:
                position = ps.update_position(session, position.id, psc.PositionUpdate(**payload))
                action = "updated"
            else:
                position = ps.create_position(session, psc.PositionCreate(account_id=account.id, instrument_id=instrument.id, **payload))
                action = "created"
            return _json_ok(action=action, position={**_portfolio_dump(position), **ps.position_metrics(session, position)})
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_add_research_report(
    title: str,
    symbol: str = "",
    market: str = "US",
    report_type: str = "research",
    summary: str = "",
    content: str = "",
    content_path: str = "",
    rating: str = "",
    confidence: float | None = None,
    evidence: list[dict[str, Any]] | None = None,
    generated_by: str = "mcp",
) -> str:
    """Save an investment research report into the workspace."""
    try:
        from src.portfolio import service as ps
        from src.portfolio import schemas as psc

        with _portfolio_session_scope() as session:
            instrument_id = None
            if symbol:
                instrument = ps.find_instrument(session, symbol, market)
                instrument_id = instrument.id if instrument else None
            report = ps.create_research_report(
                session,
                psc.ResearchReportCreate(
                    instrument_id=instrument_id,
                    title=title,
                    report_type=report_type,
                    summary=_blank_to_none(summary),
                    content=_blank_to_none(content),
                    content_path=_blank_to_none(content_path),
                    rating=_blank_to_none(rating),
                    confidence=confidence,
                    evidence=evidence or [],
                    generated_by=generated_by,
                ),
            )
            return _json_ok(report=_portfolio_dump(report))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_record_decision(
    decision_type: str,
    title: str,
    rationale: str,
    symbol: str = "",
    market: str = "US",
    expected_outcome: str = "",
    review_date: str = "",
    linked_report_id: str = "",
) -> str:
    """Record an investment decision such as buy/sell/hold/watch/rebalance."""
    try:
        from src.portfolio import service as ps
        from src.portfolio import schemas as psc

        with _portfolio_session_scope() as session:
            instrument_id = None
            if symbol:
                instrument = ps.find_instrument(session, symbol, market)
                instrument_id = instrument.id if instrument else None
            decision = ps.create_decision(
                session,
                psc.DecisionLogCreate(
                    instrument_id=instrument_id,
                    decision_type=decision_type,
                    title=title,
                    rationale=rationale,
                    expected_outcome=_blank_to_none(expected_outcome),
                    review_date=_portfolio_parse_datetime(review_date) if review_date else None,
                    linked_report_id=_blank_to_none(linked_report_id),
                ),
            )
            return _json_ok(decision=_portfolio_dump(decision))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio")


@mcp.tool
def portfolio_upload_position_screenshot(
    image_path: str = "",
    image_base64: str = "",
    filename: str = "position_screenshot.png",
    content_type: str = "image/png",
) -> str:
    """Upload a holdings screenshot and create a reviewable import job.

    Provide either image_path or image_base64. Parsed rows must still pass
    completeness checks before portfolio_confirm_import can save them.
    """
    try:
        import base64

        from src.portfolio import import_service as pis

        if image_path:
            path = Path(image_path).expanduser()
            content = path.read_bytes()
            filename = path.name
        elif image_base64:
            content = base64.b64decode(image_base64)
        else:
            raise ValueError("image_path or image_base64 is required")
        with _portfolio_session_scope() as session:
            job = pis.create_import_job(session, filename=filename, content=content, content_type=content_type)
            return _json_ok(import_job=pis.import_job_payload(session, job))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio_import")


@mcp.tool
def portfolio_update_import_job(job_id: str, broker: str = "", account_name: str = "", summary: str = "", items: list[dict[str, Any]] | None = None) -> str:
    """Patch a holdings screenshot import job after human review.

    Args:
        job_id: Import job id.
        broker: Optional broker/source.
        account_name: Optional account name.
        summary: Optional review summary.
        items: Optional ordered list of corrected import item fields.
    """
    try:
        from src.portfolio import import_service as pis
        from src.portfolio import schemas as psc

        payload = psc.PositionImportJobPatch(
            broker=_blank_to_none(broker),
            account_name=_blank_to_none(account_name),
            summary=_blank_to_none(summary),
            items=[psc.PositionImportItemPatch(**item) for item in (items or [])] if items is not None else None,
        )
        with _portfolio_session_scope() as session:
            job = pis.patch_import_job(session, job_id, payload)
            return _json_ok(import_job=pis.import_job_payload(session, job))
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio_import")


@mcp.tool
def portfolio_confirm_import(
    job_id: str,
    account_name: str = "",
    broker: str = "",
    overwrite_existing: bool = True,
    save_price_snapshots: bool = True,
) -> str:
    """Confirm a reviewed screenshot import job and save positions to the workspace."""
    try:
        from src.portfolio import import_service as pis
        from src.portfolio import schemas as psc

        with _portfolio_session_scope() as session:
            result = pis.confirm_import_job(
                session,
                job_id,
                psc.PositionImportConfirmRequest(
                    account_name=_blank_to_none(account_name),
                    broker=_blank_to_none(broker),
                    overwrite_existing=overwrite_existing,
                    save_price_snapshots=save_price_snapshots,
                ),
            )
            return _json_ok(**result)
    except Exception as exc:
        return _json_error(str(exc), error_type="portfolio_import")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Entry point for `vibe-trading-mcp` CLI command."""
    global _include_shell_tools, _registry
    import argparse

    parser = argparse.ArgumentParser(description="Vibe-Trading MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport (default: stdio)")
    parser.add_argument("--port", type=int, default=8900, help="SSE port (only used with --transport sse)")
    parser.add_argument("--host", default="0.0.0.0", help="SSE host (only used with --transport sse)")
    args = parser.parse_args()
    _include_shell_tools = True if args.transport == "stdio" else _env_shell_tools_enabled()
    _registry = None
    _get_registry()  # pre-warm: avoids deadlock when first tools/call lazy-inits inside FastMCP worker thread

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
