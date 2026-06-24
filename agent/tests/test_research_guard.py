"""Tests for finance research grounding guardrails."""

from __future__ import annotations

from src.agent.research_guard import (
    is_financial_research_task,
    is_grounding_tool,
    resolve_grounding_policy,
)


def test_finance_research_keywords_require_grounding(monkeypatch) -> None:
    monkeypatch.setenv("VIBE_RESEARCH_GROUNDING", "auto")

    policy = resolve_grounding_policy("帮我分析 BTC 今天的走势")

    assert policy.required is True
    assert policy.reason == "research_keywords"


def test_non_research_task_does_not_require_grounding(monkeypatch) -> None:
    monkeypatch.setenv("VIBE_RESEARCH_GROUNDING", "auto")

    policy = resolve_grounding_policy("把项目启动脚本整理一下")

    assert policy.required is False


def test_required_mode_forces_grounding(monkeypatch) -> None:
    monkeypatch.setenv("VIBE_RESEARCH_GROUNDING", "required")

    policy = resolve_grounding_policy("普通问题")

    assert policy.required is True
    assert policy.reason == "configured_required"


def test_grounding_tool_classifier() -> None:
    assert is_grounding_tool("get_market_data")
    assert is_grounding_tool("read_url")
    assert is_grounding_tool("bash")
    assert not is_grounding_tool("load_skill")
    assert not is_grounding_tool("write_file")


def test_symbol_like_prompt_counts_as_research() -> None:
    assert is_financial_research_task("TSLA 怎么看")
