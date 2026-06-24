"""Runtime guardrails for data-grounded finance research tasks."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable


_RESEARCH_KEYWORDS = (
    "研究", "研报", "分析", "行情", "走势", "价格", "估值", "财报", "新闻",
    "政策", "宏观", "市场", "资金流", "成交量", "换手", "技术面", "基本面",
    "股票", "港股", "美股", "a股", "a-share", "crypto", "加密", "币",
    "btc", "eth", "基金", "etf", "债券", "期货", "期权", "外汇", "利率",
    "earnings", "valuation", "market", "price", "stock", "ticker",
)

_SYMBOL_PATTERNS = (
    re.compile(r"\b[A-Z]{1,6}(?:\.[A-Z]{1,3})?\b"),
    re.compile(r"\b\d{6}\.(?:SH|SZ|BJ)\b", re.IGNORECASE),
    re.compile(r"\b(?:BTC|ETH|SOL|BNB|XRP|DOGE|ADA|AVAX|LINK|TON)[-/]?USDT?\b", re.IGNORECASE),
)

_GROUNDING_TOOLS = {
    "get_market_data",
    "read_url",
    "read_document",
    "factor_analysis",
    "options_pricing",
    "backtest",
    "run_swarm",
    "analyze_trade_journal",
    "extract_shadow_strategy",
    "run_shadow_backtest",
    "render_shadow_report",
    "scan_shadow_signals",
    "bash",
}

_GENERIC_NON_GROUNDING_TOOLS = {
    "load_skill",
    "read_file",
    "write_file",
    "edit_file",
    "remember",
    "compact",
    "save_skill",
    "patch_skill",
}

GROUNDING_PROMPT = """## Data Grounding Requirement (HARD RULE)

For financial research, market analysis, trading ideas, price/valuation/news/macro/company/fund/crypto questions, you MUST call at least one relevant data or web/document tool before giving a final answer.

Do not answer from model memory alone. Use tools such as get_market_data, read_url, read_document, factor_analysis, options_pricing, backtest, bash, or run_swarm when appropriate. The final answer must mention the data/tools used. If no suitable tool is available or a tool fails, say exactly what data is missing instead of inventing facts.
"""

GROUNDING_RETRY_PROMPT = (
    "[SYSTEM] This is a financial research / market analysis task. You have not "
    "used any data, web, document, analysis, or market-data tool yet. Call an "
    "appropriate grounding tool now before giving a final answer. Do not answer "
    "from model memory alone."
)

GROUNDING_FAILURE_MESSAGE = (
    "本次任务需要实时数据或外部资料支撑，但模型没有调用任何取数/检索/分析工具。"
    "为避免凭记忆编造结论，已拒绝生成未验证的最终回答。请检查可用工具或重试。"
)


@dataclass(frozen=True)
class GroundingPolicy:
    """Resolved research grounding policy for one task."""

    mode: str
    required: bool
    reason: str


def resolve_grounding_policy(prompt: str, *, force_data_agent: bool = False) -> GroundingPolicy:
    """Resolve whether a task must be grounded by at least one data/tool call."""
    mode = os.getenv("VIBE_RESEARCH_GROUNDING", "auto").strip().lower() or "auto"
    if mode in {"0", "false", "off", "disabled"}:
        return GroundingPolicy(mode="off", required=False, reason="disabled")
    if mode in {"1", "true", "required", "always", "on"}:
        return GroundingPolicy(mode="required", required=True, reason="configured_required")
    if force_data_agent:
        return GroundingPolicy(mode="auto", required=True, reason="data_agent")
    if is_financial_research_task(prompt):
        return GroundingPolicy(mode="auto", required=True, reason="research_keywords")
    return GroundingPolicy(mode="auto", required=False, reason="not_research")


def is_financial_research_task(prompt: str) -> bool:
    """Heuristic classifier for finance tasks that need fresh grounding."""
    text = (prompt or "").strip()
    if not text:
        return False
    low = text.lower()
    if any(keyword in low for keyword in _RESEARCH_KEYWORDS):
        return True
    return any(pattern.search(text) for pattern in _SYMBOL_PATTERNS)


def is_grounding_tool(tool_name: str, *, available_tools: Iterable[str] | None = None) -> bool:
    """Return whether a successful tool call counts as data grounding."""
    name = (tool_name or "").strip()
    if not name or name in _GENERIC_NON_GROUNDING_TOOLS:
        return False
    if name in _GROUNDING_TOOLS:
        return True
    if name.startswith(("mcp__", "remote__", "web_", "market_", "data_")):
        return True
    if available_tools is not None and name in set(available_tools) - _GENERIC_NON_GROUNDING_TOOLS:
        return True
    return False
