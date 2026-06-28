"""Screenshot import pipeline for portfolio positions."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from . import models as m
from . import schemas as s
from . import service


AGENT_DIR = Path(__file__).resolve().parents[2]
IMPORT_DIR = Path(os.getenv("VIBE_PORTFOLIO_IMPORT_DIR", str(AGENT_DIR / "uploads" / "portfolio_imports")))
REQUIRED_FIELDS = ["symbol", "name", "quantity", "avg_cost", "market", "currency"]
LOW_CONFIDENCE_THRESHOLD = 0.7


def _clean_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("，", "")
    text = text.replace("%", "")
    if text in {"-", "--", "—", "N/A", "nan"}:
        return None
    text = re.sub(r"[^\d.\-+]", "", text)
    if text in {"", "-", "+", "."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _norm_symbol(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _norm_market(symbol: str | None, value: Any) -> str | None:
    if value:
        return str(value).strip().upper()
    if not symbol:
        return None
    if re.match(r"^(6|9)\d{5}$", symbol):
        return "CN-SH"
    if re.match(r"^(0|2|3)\d{5}$", symbol):
        return "CN-SZ"
    if re.match(r"^\d{5}$", symbol):
        return "HK"
    return "US"


def _norm_currency(market: str | None, value: Any) -> str:
    if value:
        return str(value).strip().upper()
    if market in {"CN", "CN-SH", "CN-SZ"}:
        return "CNY"
    if market == "HK":
        return "HKD"
    return "USD"


def _validate_item(data: dict[str, Any]) -> tuple[list[str], list[str], str]:
    missing = [field for field in REQUIRED_FIELDS if data.get(field) in (None, "")]
    warnings: list[str] = []
    if data.get("quantity") is not None and data["quantity"] < 0:
        warnings.append("持仓数量为负数，请核实是否为截图识别错误")
    if data.get("avg_cost") is not None and data["avg_cost"] < 0:
        warnings.append("成本价为负数，请人工核实")
    if data.get("market_price") is not None and data["market_price"] < 0:
        warnings.append("当前价为负数，请人工核实")
    if data.get("confidence", 0) < LOW_CONFIDENCE_THRESHOLD:
        warnings.append("识别置信度较低，请人工核实")
    status = "ready" if not missing else "needs_review"
    return missing, warnings, status


def _normalize_item(raw: dict[str, Any], row_index: int) -> dict[str, Any]:
    symbol = _norm_symbol(raw.get("symbol") or raw.get("code") or raw.get("ticker"))
    market = _norm_market(symbol, raw.get("market") or raw.get("exchange"))
    currency = _norm_currency(market, raw.get("currency"))
    quantity = _clean_number(raw.get("quantity") or raw.get("shares") or raw.get("holding_quantity"))
    avg_cost = _clean_number(raw.get("avg_cost") or raw.get("cost_price") or raw.get("cost") or raw.get("average_cost"))
    cost_basis = _clean_number(raw.get("cost_basis") or raw.get("holding_cost") or raw.get("total_cost"))
    market_price = _clean_number(raw.get("market_price") or raw.get("price") or raw.get("last_price"))
    market_value = _clean_number(raw.get("market_value") or raw.get("value"))
    pnl = _clean_number(raw.get("unrealized_pnl") or raw.get("pnl") or raw.get("profit_loss"))
    pnl_pct = _clean_number(raw.get("unrealized_pnl_pct") or raw.get("pnl_pct") or raw.get("profit_loss_pct"))
    if pnl_pct is not None and abs(pnl_pct) > 1:
        pnl_pct = pnl_pct / 100
    if cost_basis is None and quantity is not None and avg_cost is not None:
        cost_basis = quantity * avg_cost
    if market_value is None and quantity is not None and market_price is not None:
        market_value = quantity * market_price
    confidence = _clean_number(raw.get("confidence")) or 0.85
    data = {
        "row_index": row_index,
        "symbol": symbol,
        "name": (str(raw.get("name") or raw.get("security_name") or "").strip() or symbol),
        "market": market,
        "asset_class": str(raw.get("asset_class") or "equity").strip().lower(),
        "currency": currency,
        "quantity": quantity,
        "available_quantity": _clean_number(raw.get("available_quantity") or raw.get("available")),
        "avg_cost": avg_cost,
        "cost_basis": cost_basis,
        "market_price": market_price,
        "market_value": market_value,
        "unrealized_pnl": pnl,
        "unrealized_pnl_pct": pnl_pct,
        "confidence": max(0.0, min(1.0, confidence)),
        "field_confidence": raw.get("field_confidence") or {},
        "source_text": raw.get("source_text"),
        "raw": raw,
    }
    missing, warnings, status = _validate_item(data)
    data["missing_fields"] = missing
    data["warnings"] = warnings
    data["status"] = status
    return data


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if match:
        return json.loads(match.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("Vision model did not return JSON")


def _vision_config() -> tuple[str | None, str | None, str | None]:
    api_key = os.getenv("VIBE_PORTFOLIO_IMPORT_API_KEY") or os.getenv("MINIMAX_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = (
        os.getenv("VIBE_PORTFOLIO_IMPORT_BASE_URL")
        or os.getenv("MINIMAX_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    model = os.getenv("VIBE_PORTFOLIO_IMPORT_MODEL") or os.getenv("LANGCHAIN_MODEL_NAME") or os.getenv("OPENAI_MODEL")
    return api_key, base_url.rstrip("/") if base_url else None, model


def _prompt() -> str:
    return (
        "你是金融持仓截图结构化解析器。请从截图中提取所有持仓行，只返回 JSON，不要输出解释。"
        "JSON 格式：{\"broker\": string|null, \"account_name\": string|null, \"summary\": string|null, "
        "\"positions\": [{\"symbol\": string|null, \"name\": string|null, \"market\": string|null, "
        "\"asset_class\": string|null, \"currency\": string|null, \"quantity\": number|null, "
        "\"available_quantity\": number|null, \"avg_cost\": number|null, \"cost_basis\": number|null, "
        "\"market_price\": number|null, \"market_value\": number|null, \"unrealized_pnl\": number|null, "
        "\"unrealized_pnl_pct\": number|null, \"confidence\": number, \"field_confidence\": object, "
        "\"source_text\": string|null}]}. 数字不要带货币符号、千分位或百分号；百分比用小数，例如 12.3% 返回 0.123。"
    )


def _parse_with_vision(file_path: Path, content_type: str | None) -> tuple[dict[str, Any], str]:
    api_key, base_url, model = _vision_config()
    if not api_key or not base_url or not model:
        raise RuntimeError("未配置截图解析视觉模型，请设置 VIBE_PORTFOLIO_IMPORT_API_KEY/BASE_URL/MODEL 或可复用的模型环境变量")
    mime = content_type or mimetypes.guess_type(file_path.name)[0] or "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(file_path.read_bytes()).decode('ascii')}"
    timeout = httpx.Timeout(120.0)
    if "/anthropic" in base_url:
        url = f"{base_url}/v1/messages" if not base_url.endswith("/v1/messages") else base_url
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt()},
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data_url.split(",", 1)[1]}},
                ],
            }],
        }
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        with httpx.Client(timeout=timeout) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            body = res.json()
        text = "".join(part.get("text", "") for part in body.get("content", []) if part.get("type") == "text")
        return _extract_json(text), "anthropic_vision"

    url = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _prompt()},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=timeout) as client:
        res = client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
        res.raise_for_status()
        body = res.json()
    text = body["choices"][0]["message"]["content"]
    return _extract_json(text), "openai_vision"


def _fallback_result(error: Exception) -> dict[str, Any]:
    return {
        "broker": None,
        "account_name": None,
        "summary": f"截图已上传，但自动解析失败：{error}",
        "positions": [],
        "warnings": ["自动解析失败，请人工录入持仓明细后再确认保存"],
    }


def create_import_job(session, *, filename: str, content: bytes, content_type: str | None) -> m.PositionImportJob:
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("_") or "position_screenshot.png"
    path = IMPORT_DIR / f"{m.new_id()}_{safe_name}"
    path.write_bytes(content)
    job = m.PositionImportJob(filename=filename, file_path=str(path), content_type=content_type, status="uploaded")
    session.add(job)
    session.flush()
    parse_import_job(session, job.id)
    return get_import_job(session, job.id) or job


def parse_import_job(session, job_id: str) -> m.PositionImportJob:
    job = session.get(m.PositionImportJob, job_id)
    if not job:
        raise ValueError("Import job not found")
    try:
        raw, parser = _parse_with_vision(Path(job.file_path), job.content_type)
    except Exception as exc:
        raw, parser = _fallback_result(exc), "fallback"
    job.parser = parser
    job.raw_result = raw
    job.broker = raw.get("broker") or job.broker
    job.account_name = raw.get("account_name") or job.account_name
    job.summary = raw.get("summary")
    job.warnings = raw.get("warnings") or []
    for old in session.execute(select(m.PositionImportItem).where(m.PositionImportItem.job_id == job.id)).scalars():
        session.delete(old)
    positions = raw.get("positions") or raw.get("items") or []
    for idx, raw_item in enumerate(positions, start=1):
        data = _normalize_item(raw_item or {}, idx)
        session.add(m.PositionImportItem(job_id=job.id, **data))
    session.flush()
    _revalidate_job(session, job)
    return job


def _revalidate_job(session, job: m.PositionImportJob) -> None:
    items = list(session.execute(select(m.PositionImportItem).where(m.PositionImportItem.job_id == job.id)).scalars())
    missing = sorted({field for item in items for field in (item.missing_fields or [])})
    warnings = list(job.warnings or [])
    if not items:
        warnings.append("未识别到持仓明细，请人工补录")
    job.missing_fields = missing
    job.warnings = list(dict.fromkeys(warnings))
    if not items or any(item.status == "needs_review" for item in items):
        job.status = "needs_review"
    else:
        job.status = "ready_to_save"


def get_import_job(session, job_id: str) -> m.PositionImportJob | None:
    return session.execute(
        select(m.PositionImportJob)
        .options(joinedload(m.PositionImportJob.items) if hasattr(m.PositionImportJob, "items") else joinedload("*"))
        .where(m.PositionImportJob.id == job_id)
    ).unique().scalar_one_or_none()


def list_import_jobs(session, limit: int = 20) -> list[m.PositionImportJob]:
    return list(
        session.execute(select(m.PositionImportJob).order_by(m.PositionImportJob.created_at.desc()).limit(limit)).scalars()
    )


def import_job_payload(session, job: m.PositionImportJob) -> dict[str, Any]:
    items = list(
        session.execute(
            select(m.PositionImportItem).where(m.PositionImportItem.job_id == job.id).order_by(m.PositionImportItem.row_index)
        ).scalars()
    )
    return {**job.__dict__, "items": items}


def patch_import_job(session, job_id: str, payload: s.PositionImportJobPatch) -> m.PositionImportJob:
    job = session.get(m.PositionImportJob, job_id)
    if not job:
        raise ValueError("Import job not found")
    data = payload.model_dump(exclude_unset=True)
    for key in ("broker", "account_name", "summary"):
        if key in data:
            setattr(job, key, data[key])
    if payload.items is not None:
        existing = list(session.execute(select(m.PositionImportItem).where(m.PositionImportItem.job_id == job.id)).scalars())
        by_index = {item.row_index: item for item in existing}
        for idx, item_payload in enumerate(payload.items, start=1):
            values = item_payload.model_dump(exclude_unset=True)
            item = by_index.get(idx)
            if not item:
                item = m.PositionImportItem(job_id=job.id, row_index=idx)
                session.add(item)
            for key, value in values.items():
                setattr(item, key, value)
            normalized = _normalize_item({**item.raw, **values}, idx)
            for key in ("symbol", "name", "market", "asset_class", "currency", "quantity", "available_quantity", "avg_cost", "cost_basis", "market_price", "market_value", "unrealized_pnl", "unrealized_pnl_pct", "missing_fields", "warnings", "status"):
                setattr(item, key, normalized[key])
            item.confidence = max(item.confidence or 0, 1.0 if not item.missing_fields else 0.6)
    session.flush()
    _revalidate_job(session, job)
    return job


def _account_for_import(session, name: str | None, broker: str | None) -> m.PortfolioAccount:
    account_name = name or "Imported Holdings"
    account = session.execute(select(m.PortfolioAccount).where(m.PortfolioAccount.name == account_name).limit(1)).scalar_one_or_none()
    if account:
        if broker and not account.broker:
            account.broker = broker
        return account
    account = m.PortfolioAccount(name=account_name, broker=broker or "screenshot", account_type="manual")
    session.add(account)
    session.flush()
    return account


def confirm_import_job(session, job_id: str, payload: s.PositionImportConfirmRequest) -> dict[str, Any]:
    job = session.get(m.PositionImportJob, job_id)
    if not job:
        raise ValueError("Import job not found")
    items = list(session.execute(select(m.PositionImportItem).where(m.PositionImportItem.job_id == job.id)).scalars())
    not_ready = [item.id for item in items if item.status not in {"ready", "skipped"} or (item.status == "ready" and item.missing_fields)]
    if not_ready:
        raise ValueError(f"存在未完成核实的持仓明细：{', '.join(not_ready)}")
    account = _account_for_import(session, payload.account_name or job.account_name, payload.broker or job.broker)
    saved: list[str] = []
    skipped: list[str] = []
    for item in items:
        if item.status == "skipped":
            skipped.append(item.id)
            continue
        instrument = service.find_instrument(session, item.symbol or "", item.market or "US")
        if not instrument:
            instrument = service.create_instrument(
                session,
                s.InstrumentCreate(
                    symbol=item.symbol or "",
                    name=item.name or item.symbol or "",
                    market=item.market or "US",
                    asset_class=item.asset_class or "equity",
                    currency=item.currency or "USD",
                ),
            )
        position = session.execute(
            select(m.Position)
            .where(m.Position.account_id == account.id, m.Position.instrument_id == instrument.id)
            .limit(1)
        ).scalar_one_or_none()
        cost_basis = item.cost_basis if item.cost_basis is not None else (item.quantity or 0) * (item.avg_cost or 0)
        if position:
            if not payload.overwrite_existing:
                skipped.append(item.id)
                continue
            position.quantity = item.quantity or 0
            position.avg_cost = item.avg_cost or 0
            position.cost_basis = cost_basis or 0
            position.notes = f"由截图导入任务 {job.id} 更新"
        else:
            position = service.create_position(
                session,
                s.PositionCreate(
                    account_id=account.id,
                    instrument_id=instrument.id,
                    quantity=item.quantity or 0,
                    avg_cost=item.avg_cost or 0,
                    cost_basis=cost_basis,
                    notes=f"由截图导入任务 {job.id} 创建",
                ),
            )
        if payload.save_price_snapshots and item.market_price is not None:
            service.add_price_snapshot(
                session,
                s.PriceSnapshotCreate(
                    instrument_id=instrument.id,
                    price=item.market_price,
                    source="screenshot_import",
                    raw={"import_job_id": job.id, "import_item_id": item.id},
                ),
            )
        item.status = "saved"
        item.saved_position_id = position.id
        saved.append(position.id)
    job.status = "saved"
    job.saved_at = datetime.utcnow()
    session.flush()
    return {"status": "ok", "job_id": job.id, "saved_positions": saved, "skipped_items": skipped}
