from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    ClarificationItem,
    ControlException,
    Engagement,
    EngagementStatus,
    Entity,
    FileType,
    FXRate,
    OutputArtifact,
    RateType,
    UploadedFile,
)
from ..schemas import (
    ArtifactRow,
    ClarificationStatus,
    ClarificationSubmission,
    EngagementCreate,
    EngagementSummary,
    EntityCreate,
    ExceptionRow,
    FXOverrideRequest,
    FXRateRow,
    ProcessResponse,
)
from ..security import require_api_key
from ..services.common import add_audit_event
from ..services.pipeline_service import clarification_status, process_engagement, retrieve_fx_for_engagement
from ..services.storage_service import save_upload

router = APIRouter(prefix="/api", tags=["consolidation"], dependencies=[Depends(require_api_key)])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _build_katanox_auth_header(x_katanox_token: str | None) -> str:
    if not x_katanox_token or not x_katanox_token.strip():
        raise HTTPException(
            status_code=400,
            detail="X-Katanox-Token header is required",
        )

    token = x_katanox_token.strip()
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def _katanox_request(
    method: str,
    path: str,
    x_katanox_token: str | None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> JSONResponse | Response:
    authorization = _build_katanox_auth_header(x_katanox_token)

    try:
        with httpx.Client(
            base_url=settings.katanox_base_url,
            timeout=settings.katanox_timeout_seconds,
        ) as client:
            response = client.request(
                method=method,
                url=path,
                headers={"Authorization": authorization},
                params=params,
                json=body,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Katanox request failed: {exc}") from exc

    if response.status_code == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    content_type = response.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        payload = response.json()
    else:
        payload = {"raw": response.text}

    return JSONResponse(status_code=response.status_code, content=payload)


@router.get("/katanox/properties", tags=["katanox"])
def katanox_get_properties(
    property_ids: list[str] | None = Query(default=None),
    x_katanox_token: str | None = Header(default=None, alias="X-Katanox-Token"),
) -> JSONResponse | Response:
    params: dict[str, Any] = {}
    if property_ids:
        params["property_ids"] = property_ids
    return _katanox_request("GET", "/properties", x_katanox_token, params=params or None)


@router.get("/katanox/availability", tags=["katanox"])
def katanox_get_availability(
    check_in: str = Query(..., description="Date in YYYY-MM-DD"),
    check_out: str = Query(..., description="Date in YYYY-MM-DD"),
    adults: int = Query(default=1, ge=1),
    children: int = Query(default=0, ge=0),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
    radius: int = Query(default=2000, ge=1),
    property_ids: list[str] | None = Query(default=None),
    corporate_profile_id: str | None = Query(default=None),
    number_of_units: int = Query(default=1, ge=1),
    page: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
    lowest: bool = Query(default=False),
    price_breakdown: bool = Query(default=False),
    unit_type: str | None = Query(default=None),
    occupancy: str | None = Query(default=None),
    separate_rates_per_payment: bool = Query(default=False),
    x_katanox_token: str | None = Header(default=None, alias="X-Katanox-Token"),
) -> JSONResponse | Response:
    using_property_ids = bool(property_ids)
    using_coordinates = lat is not None and lng is not None

    if not using_property_ids and not using_coordinates:
        raise HTTPException(
            status_code=400,
            detail="Provide either property_ids or both lat and lng.",
        )
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=400,
            detail="lat and lng must be provided together.",
        )

    params: dict[str, Any] = {
        "check_in": check_in,
        "check_out": check_out,
        "adults": adults,
        "children": children,
        "number_of_units": number_of_units,
        "lowest": lowest,
        "price_breakdown": price_breakdown,
        "separate_rates_per_payment": separate_rates_per_payment,
    }
    if property_ids:
        params["property_ids"] = property_ids
    if using_coordinates:
        params["lat"] = lat
        params["lng"] = lng
        params["radius"] = radius
        params["page"] = page
        params["limit"] = limit
    if corporate_profile_id:
        params["corporate_profile_id"] = corporate_profile_id
    if unit_type:
        params["unit_type"] = unit_type
    if occupancy:
        params["occupancy"] = occupancy

    return _katanox_request("GET", "/availability", x_katanox_token, params=params)


@router.get("/katanox/bookings/{booking_id}", tags=["katanox"])
def katanox_get_booking(
    booking_id: str,
    x_katanox_token: str | None = Header(default=None, alias="X-Katanox-Token"),
) -> JSONResponse | Response:
    return _katanox_request("GET", f"/bookings/{booking_id}", x_katanox_token)


@router.post("/katanox/bookings", tags=["katanox"])
def katanox_create_booking(
    payload: dict[str, Any] = Body(...),
    x_katanox_token: str | None = Header(default=None, alias="X-Katanox-Token"),
) -> JSONResponse | Response:
    return _katanox_request("POST", "/bookings", x_katanox_token, body=payload)


@router.post("/engagements", response_model=EngagementSummary)
def create_engagement(payload: EngagementCreate, db: Session = Depends(get_db)) -> Engagement:
    engagement = Engagement(name=payload.name, status=EngagementStatus.CLARIFICATION_PENDING.value)
    db.add(engagement)
    add_audit_event(db, "engagement_created", "user", {"name": payload.name}, engagement.id)
    db.commit()
    db.refresh(engagement)
    return engagement


@router.get("/engagements", response_model=list[EngagementSummary])
def list_engagements(db: Session = Depends(get_db)) -> list[Engagement]:
    rows = db.execute(select(Engagement).order_by(Engagement.created_at.desc())).scalars().all()
    return list(rows)


@router.get("/engagements/{engagement_id}", response_model=EngagementSummary)
def get_engagement(engagement_id: str, db: Session = Depends(get_db)) -> Engagement:
    row = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return row


@router.post("/engagements/{engagement_id}/entities")
def add_entity(engagement_id: str, payload: EntityCreate, db: Session = Depends(get_db)) -> dict:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    entity = Entity(
        engagement_id=engagement_id,
        name=payload.name,
        functional_currency=payload.functional_currency,
        ownership_pct=payload.ownership_pct,
        has_nci=payload.has_nci,
        include_in_scope=payload.include_in_scope,
        intercompany_identifier=payload.intercompany_identifier,
    )
    db.add(entity)
    add_audit_event(
        db,
        "entity_added",
        "user",
        {
            "entity_name": payload.name,
            "functional_currency": payload.functional_currency,
            "ownership_pct": str(payload.ownership_pct),
        },
        engagement_id,
    )
    db.commit()
    db.refresh(entity)
    return {"entity_id": entity.id, "name": entity.name}


@router.put("/engagements/{engagement_id}/clarification", response_model=ClarificationStatus)
def submit_clarification(
    engagement_id: str,
    payload: ClarificationSubmission,
    db: Session = Depends(get_db),
) -> ClarificationStatus:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    if payload.reporting_period_start > payload.reporting_period_end:
        raise HTTPException(status_code=400, detail="Reporting period start must be before end")

    engagement.reporting_period_start = payload.reporting_period_start
    engagement.reporting_period_end = payload.reporting_period_end
    engagement.presentation_currency = payload.presentation_currency
    engagement.average_method = payload.average_method
    engagement.intercompany_method = payload.intercompany_method

    entities = {
        entity.id: entity
        for entity in db.execute(select(Entity).where(Entity.engagement_id == engagement_id)).scalars().all()
    }

    submitted_ids = {item.entity_id for item in payload.entities}
    for entity_id in submitted_ids:
        if entity_id not in entities:
            raise HTTPException(status_code=400, detail=f"Unknown entity ID in clarification: {entity_id}")

    for item in payload.entities:
        entity = entities[item.entity_id]
        entity.functional_currency = item.functional_currency
        entity.ownership_pct = item.ownership_pct
        entity.has_nci = item.has_nci
        entity.intercompany_identifier = item.intercompany_identifier
        entity.include_in_scope = item.include_in_scope

    db.execute(delete(ClarificationItem).where(ClarificationItem.engagement_id == engagement_id))

    db.add_all(
        [
            ClarificationItem(engagement_id=engagement_id, key="entities_included", value=",".join(sorted(submitted_ids))),
            ClarificationItem(
                engagement_id=engagement_id,
                key="reporting_period_start",
                value=payload.reporting_period_start.isoformat(),
            ),
            ClarificationItem(
                engagement_id=engagement_id,
                key="reporting_period_end",
                value=payload.reporting_period_end.isoformat(),
            ),
            ClarificationItem(
                engagement_id=engagement_id,
                key="functional_currency_by_entity",
                value=",".join(f"{i.entity_id}:{i.functional_currency}" for i in payload.entities),
            ),
            ClarificationItem(
                engagement_id=engagement_id,
                key="ownership_by_entity",
                value=",".join(f"{i.entity_id}:{i.ownership_pct}" for i in payload.entities),
            ),
            ClarificationItem(
                engagement_id=engagement_id,
                key="nci_confirmed",
                value=",".join(f"{i.entity_id}:{'Y' if i.has_nci else 'N'}" for i in payload.entities),
            ),
            ClarificationItem(
                engagement_id=engagement_id,
                key="intercompany_identifiable",
                value=payload.intercompany_method,
            ),
            ClarificationItem(
                engagement_id=engagement_id,
                key="presentation_currency",
                value=payload.presentation_currency,
            ),
        ]
    )

    ready, missing = clarification_status(db, engagement)
    engagement.status = (
        EngagementStatus.READY_TO_PROCESS.value if ready else EngagementStatus.CLARIFICATION_PENDING.value
    )
    add_audit_event(
        db,
        "clarification_submitted",
        "user",
        {
            "ready": ready,
            "missing": missing,
            "period_start": payload.reporting_period_start.isoformat(),
            "period_end": payload.reporting_period_end.isoformat(),
            "presentation_currency": payload.presentation_currency,
        },
        engagement_id,
    )

    db.commit()
    return ClarificationStatus(ready=ready, missing_items=missing)


@router.get("/engagements/{engagement_id}/clarification/status", response_model=ClarificationStatus)
def get_clarification_status(engagement_id: str, db: Session = Depends(get_db)) -> ClarificationStatus:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    ready, missing = clarification_status(db, engagement)
    return ClarificationStatus(ready=ready, missing_items=missing)


@router.post("/engagements/{engagement_id}/uploads")
def upload_file(
    engagement_id: str,
    file_type: str = Query(..., description="ENTITY_TB | ENTITY_GL | CONSOLIDATION_TEMPLATE | COA_MAPPING"),
    entity_id: str | None = Query(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    try:
        allowed_file_type = FileType(file_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{file_type}'") from exc

    if allowed_file_type in {FileType.ENTITY_TB, FileType.ENTITY_GL} and not entity_id:
        raise HTTPException(status_code=400, detail="entity_id is required for ENTITY_TB / ENTITY_GL uploads")

    if entity_id:
        entity_exists = db.execute(
            select(Entity).where(and_(Entity.id == entity_id, Entity.engagement_id == engagement_id))
        ).scalar_one_or_none()
        if not entity_exists:
            raise HTTPException(status_code=400, detail="Invalid entity_id for this engagement")

    path, checksum = save_upload(file, engagement_id, entity_id)
    row = UploadedFile(
        engagement_id=engagement_id,
        entity_id=entity_id,
        file_type=allowed_file_type.value,
        original_name=file.filename or "upload",
        storage_path=str(path),
        checksum_sha256=checksum,
        metadata_json={"content_type": file.content_type},
    )
    db.add(row)
    add_audit_event(
        db,
        "file_uploaded",
        "user",
        {
            "file_type": allowed_file_type.value,
            "entity_id": entity_id,
            "original_name": file.filename,
            "checksum": checksum,
        },
        engagement_id,
    )
    db.commit()
    db.refresh(row)

    return {
        "file_id": row.id,
        "file_type": row.file_type,
        "entity_id": row.entity_id,
        "original_name": row.original_name,
        "checksum_sha256": row.checksum_sha256,
    }


@router.post("/engagements/{engagement_id}/fx/retrieve", response_model=list[FXRateRow])
def retrieve_fx(engagement_id: str, db: Session = Depends(get_db)) -> list[FXRateRow]:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    retrieve_fx_for_engagement(db, engagement)
    db.commit()

    entities = {entity.id: entity.name for entity in engagement.entities}
    rows = db.execute(
        select(FXRate)
        .where(FXRate.engagement_id == engagement_id)
        .order_by(FXRate.entity_id, FXRate.rate_type, FXRate.rate_date)
    ).scalars().all()

    return [
        FXRateRow(
            entity_id=row.entity_id,
            entity_name=entities.get(row.entity_id, row.entity_id),
            base_currency=row.base_currency,
            quote_currency=row.quote_currency,
            rate_type=row.rate_type,
            rate_date=row.rate_date,
            rate=row.rate,
            source=row.source,
            methodology=row.methodology,
            missing_days=row.missing_days,
            is_override=row.is_override,
        )
        for row in rows
    ]


@router.get("/engagements/{engagement_id}/fx", response_model=list[FXRateRow])
def list_fx(engagement_id: str, db: Session = Depends(get_db)) -> list[FXRateRow]:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    entities = {entity.id: entity.name for entity in engagement.entities}
    rows = db.execute(
        select(FXRate)
        .where(FXRate.engagement_id == engagement_id)
        .order_by(FXRate.entity_id, FXRate.rate_type, FXRate.rate_date)
    ).scalars().all()

    return [
        FXRateRow(
            entity_id=row.entity_id,
            entity_name=entities.get(row.entity_id, row.entity_id),
            base_currency=row.base_currency,
            quote_currency=row.quote_currency,
            rate_type=row.rate_type,
            rate_date=row.rate_date,
            rate=row.rate,
            source=row.source,
            methodology=row.methodology,
            missing_days=row.missing_days,
            is_override=row.is_override,
        )
        for row in rows
    ]


@router.post("/engagements/{engagement_id}/fx/override")
def override_fx(
    engagement_id: str,
    payload: FXOverrideRequest,
    db: Session = Depends(get_db),
) -> dict:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    entity = db.execute(
        select(Entity).where(and_(Entity.id == payload.entity_id, Entity.engagement_id == engagement_id))
    ).scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if payload.rate_type.upper() not in {RateType.CLOSING.value, RateType.AVERAGE.value, RateType.HISTORICAL.value}:
        raise HTTPException(status_code=400, detail="Invalid rate_type")

    row = FXRate(
        engagement_id=engagement_id,
        entity_id=payload.entity_id,
        source="Manual override",
        base_currency=entity.functional_currency,
        quote_currency=engagement.presentation_currency,
        rate_type=payload.rate_type.upper(),
        rate_date=payload.rate_date,
        rate=payload.rate,
        methodology="Manual override applied by user",
        missing_days=0,
        is_override=True,
        note=payload.note,
    )
    db.add(row)
    add_audit_event(
        db,
        "fx_override_added",
        "user",
        {
            "entity_id": payload.entity_id,
            "rate_type": payload.rate_type,
            "rate": str(payload.rate),
            "rate_date": payload.rate_date.isoformat(),
        },
        engagement_id,
    )
    db.commit()

    return {"status": "ok", "message": "Override recorded"}


@router.post("/engagements/{engagement_id}/process", response_model=ProcessResponse)
def run_processing(engagement_id: str, db: Session = Depends(get_db)) -> ProcessResponse:
    engagement = db.execute(select(Engagement).where(Engagement.id == engagement_id)).scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")

    message, blocking = process_engagement(db, engagement, actor="user")
    db.commit()

    return ProcessResponse(
        engagement_id=engagement.id,
        status=engagement.status,
        blocking_issues=blocking,
        message=message,
    )


@router.get("/engagements/{engagement_id}/exceptions", response_model=list[ExceptionRow])
def list_exceptions(engagement_id: str, db: Session = Depends(get_db)) -> list[ControlException]:
    rows = db.execute(
        select(ControlException)
        .where(ControlException.engagement_id == engagement_id)
        .order_by(ControlException.blocking.desc(), ControlException.created_at)
    ).scalars().all()
    return list(rows)


@router.get("/engagements/{engagement_id}/artifacts", response_model=list[ArtifactRow])
def list_artifacts(engagement_id: str, db: Session = Depends(get_db)) -> list[OutputArtifact]:
    rows = db.execute(
        select(OutputArtifact)
        .where(OutputArtifact.engagement_id == engagement_id)
        .order_by(OutputArtifact.created_at)
    ).scalars().all()
    return list(rows)


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, db: Session = Depends(get_db)) -> FileResponse:
    artifact = db.execute(select(OutputArtifact).where(OutputArtifact.id == artifact_id)).scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    file_path = Path(artifact.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact file does not exist on disk")

    return FileResponse(path=file_path, filename=file_path.name)


@router.get("/engagements/{engagement_id}/entities")
def list_entities(engagement_id: str, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Entity).where(Entity.engagement_id == engagement_id).order_by(Entity.created_at)
    ).scalars().all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "functional_currency": row.functional_currency,
            "ownership_pct": str(Decimal(row.ownership_pct)),
            "has_nci": row.has_nci,
            "include_in_scope": row.include_in_scope,
            "intercompany_identifier": row.intercompany_identifier,
        }
        for row in rows
    ]
