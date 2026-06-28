"""FastAPI router for the investment workspace."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from . import schemas as s
from .db import PortfolioDatabaseUnavailable, session_scope
from . import service
from . import import_service

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def db_session() -> Iterator[object]:
    try:
        with session_scope() as session:
            yield session
    except PortfolioDatabaseUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/health")
def health(session=Depends(db_session)):
    return {"status": "ok", "database": "connected"}


@router.get("/dashboard", response_model=s.PortfolioDashboard)
def dashboard(session=Depends(db_session)):
    return service.dashboard(session)


@router.get("/accounts", response_model=list[s.PortfolioAccountOut])
def list_accounts(session=Depends(db_session)):
    return service.list_accounts(session)


@router.post("/accounts", response_model=s.PortfolioAccountOut, status_code=201)
def create_account(payload: s.PortfolioAccountCreate, session=Depends(db_session)):
    return service.create_account(session, payload)


@router.get("/instruments", response_model=list[s.InstrumentOut])
def list_instruments(
    q: str | None = Query(None, description="按代码或名称搜索"),
    active: bool | None = Query(None, description="是否只返回启用标的"),
    session=Depends(db_session),
):
    return service.list_instruments(session, q=q, active=active)


@router.post("/instruments", response_model=s.InstrumentOut, status_code=201)
def create_instrument(payload: s.InstrumentCreate, session=Depends(db_session)):
    return service.create_instrument(session, payload)


@router.get("/instruments/{instrument_id}", response_model=s.InstrumentOut)
def get_instrument(instrument_id: str, session=Depends(db_session)):
    instrument = service.get_instrument(session, instrument_id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return instrument


@router.patch("/instruments/{instrument_id}", response_model=s.InstrumentOut)
def update_instrument(instrument_id: str, payload: s.InstrumentUpdate, session=Depends(db_session)):
    instrument = service.update_instrument(session, instrument_id, payload)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return instrument


@router.delete("/instruments/{instrument_id}")
def delete_instrument(instrument_id: str, session=Depends(db_session)):
    if not service.delete_instrument(session, instrument_id):
        raise HTTPException(status_code=404, detail="Instrument not found")
    return {"status": "ok"}


@router.get("/watchlist", response_model=list[s.WatchlistItemOut])
def list_watchlist(session=Depends(db_session)):
    return service.list_watchlist(session)


@router.post("/watchlist", response_model=s.WatchlistItemOut, status_code=201)
def create_watchlist_item(payload: s.WatchlistItemCreate, session=Depends(db_session)):
    return service.create_watchlist_item(session, payload)


@router.patch("/watchlist/{item_id}", response_model=s.WatchlistItemOut)
def update_watchlist_item(item_id: str, payload: s.WatchlistItemUpdate, session=Depends(db_session)):
    item = service.update_watchlist_item(session, item_id, payload)
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return item


@router.delete("/watchlist/{item_id}")
def delete_watchlist_item(item_id: str, session=Depends(db_session)):
    if not service.delete_watchlist_item(session, item_id):
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return {"status": "ok"}


@router.get("/positions", response_model=list[s.PositionOut])
def list_positions(session=Depends(db_session)):
    return [
        {**p.__dict__, **service.position_metrics(session, p)}
        for p in service.list_positions(session)
    ]


@router.post("/positions", response_model=s.PositionOut, status_code=201)
def create_position(payload: s.PositionCreate, session=Depends(db_session)):
    p = service.create_position(session, payload)
    return {**p.__dict__, **service.position_metrics(session, p)}


@router.get("/positions/{position_id}", response_model=s.PositionOut)
def get_position(position_id: str, session=Depends(db_session)):
    p = service.get_position(session, position_id)
    if not p:
        raise HTTPException(status_code=404, detail="Position not found")
    return {**p.__dict__, **service.position_metrics(session, p)}


@router.patch("/positions/{position_id}", response_model=s.PositionOut)
def update_position(position_id: str, payload: s.PositionUpdate, session=Depends(db_session)):
    p = service.update_position(session, position_id, payload)
    if not p:
        raise HTTPException(status_code=404, detail="Position not found")
    return {**p.__dict__, **service.position_metrics(session, p)}


@router.delete("/positions/{position_id}")
def delete_position(position_id: str, session=Depends(db_session)):
    if not service.delete_position(session, position_id):
        raise HTTPException(status_code=404, detail="Position not found")
    return {"status": "ok"}


@router.post("/position-lots", response_model=s.PositionLotOut, status_code=201)
def add_position_lot(payload: s.PositionLotCreate, session=Depends(db_session)):
    lot, _ = service.add_position_lot(session, payload)
    return lot


@router.post("/price-snapshots", response_model=s.PriceSnapshotOut, status_code=201)
def add_price_snapshot(payload: s.PriceSnapshotCreate, session=Depends(db_session)):
    return service.add_price_snapshot(session, payload)


@router.get("/research-reports", response_model=list[s.ResearchReportOut])
def list_research_reports(
    instrument_id: str | None = Query(None, description="关联标的ID"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    session=Depends(db_session),
):
    return service.list_research_reports(session, instrument_id=instrument_id, limit=limit)


@router.post("/research-reports", response_model=s.ResearchReportOut, status_code=201)
def create_research_report(payload: s.ResearchReportCreate, session=Depends(db_session)):
    return service.create_research_report(session, payload)


@router.get("/tracking-rules", response_model=list[s.TrackingRuleOut])
def list_tracking_rules(session=Depends(db_session)):
    return service.list_tracking_rules(session)


@router.post("/tracking-rules", response_model=s.TrackingRuleOut, status_code=201)
def create_tracking_rule(payload: s.TrackingRuleCreate, session=Depends(db_session)):
    return service.create_tracking_rule(session, payload)


@router.patch("/tracking-rules/{rule_id}", response_model=s.TrackingRuleOut)
def update_tracking_rule(rule_id: str, payload: s.TrackingRuleUpdate, session=Depends(db_session)):
    rule = service.update_tracking_rule(session, rule_id, payload)
    if not rule:
        raise HTTPException(status_code=404, detail="Tracking rule not found")
    return rule


@router.get("/decisions", response_model=list[s.DecisionLogOut])
def list_decisions(
    instrument_id: str | None = Query(None, description="关联标的ID"),
    limit: int = Query(30, ge=1, le=100, description="返回条数"),
    session=Depends(db_session),
):
    return service.list_decisions(session, instrument_id=instrument_id, limit=limit)


@router.post("/decisions", response_model=s.DecisionLogOut, status_code=201)
def create_decision(payload: s.DecisionLogCreate, session=Depends(db_session)):
    return service.create_decision(session, payload)


@router.get("/imports", response_model=list[s.PositionImportJobOut])
def list_position_imports(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    session=Depends(db_session),
):
    return [import_service.import_job_payload(session, job) for job in import_service.list_import_jobs(session, limit=limit)]


@router.post("/imports/screenshot", response_model=s.PositionImportJobOut, status_code=201)
async def upload_position_screenshot(file: UploadFile = File(...), session=Depends(db_session)):
    content_type = file.content_type or ""
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are supported")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    job = import_service.create_import_job(
        session,
        filename=file.filename or "position_screenshot.png",
        content=content,
        content_type=file.content_type,
    )
    return import_service.import_job_payload(session, job)


@router.get("/imports/{job_id}", response_model=s.PositionImportJobOut)
def get_position_import(job_id: str, session=Depends(db_session)):
    job = import_service.get_import_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return import_service.import_job_payload(session, job)


@router.patch("/imports/{job_id}", response_model=s.PositionImportJobOut)
def patch_position_import(job_id: str, payload: s.PositionImportJobPatch, session=Depends(db_session)):
    try:
        job = import_service.patch_import_job(session, job_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return import_service.import_job_payload(session, job)


@router.post("/imports/{job_id}/confirm", response_model=s.PositionImportConfirmResponse)
def confirm_position_import(job_id: str, payload: s.PositionImportConfirmRequest, session=Depends(db_session)):
    try:
        return import_service.confirm_import_job(session, job_id, payload)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
