from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    ClarificationItem,
    ConsolidationJournal,
    ControlException,
    Entity,
    Engagement,
    EngagementStatus,
    FileType,
    FXRate,
    NormalizedBalance,
    TranslatedBalance,
    UploadedFile,
)
from .common import add_audit_event, add_exception
from .consolidation_service import run_consolidation
from .controls_service import run_controls
from .fx_service import FXServiceError, iter_fx_rows, store_standard_rates
from .mapping_service import import_mapping_file
from .output_service import generate_all_outputs
from .parser_service import parse_trial_balance


REQUIRED_CLARIFICATION_KEYS = [
    "entities_included",
    "reporting_period_start",
    "reporting_period_end",
    "functional_currency_by_entity",
    "ownership_by_entity",
    "nci_confirmed",
    "intercompany_identifiable",
    "presentation_currency",
]


def _latest_file(
    db: Session,
    engagement_id: str,
    file_type: str,
    *,
    entity_id: str | None = None,
) -> UploadedFile | None:
    stmt = select(UploadedFile).where(
        and_(
            UploadedFile.engagement_id == engagement_id,
            UploadedFile.file_type == file_type,
        )
    )
    if entity_id is not None:
        stmt = stmt.where(UploadedFile.entity_id == entity_id)
    stmt = stmt.order_by(UploadedFile.uploaded_at.desc())
    return db.execute(stmt).scalar_one_or_none()


def clarification_status(db: Session, engagement: Engagement) -> tuple[bool, list[str]]:
    missing: list[str] = []

    if not engagement.reporting_period_start:
        missing.append("reporting_period_start")
    if not engagement.reporting_period_end:
        missing.append("reporting_period_end")
    if not engagement.presentation_currency:
        missing.append("presentation_currency")
    if not engagement.intercompany_method:
        missing.append("intercompany_method")

    entities = [entity for entity in engagement.entities if entity.include_in_scope]
    if not entities:
        missing.append("entities_included")
    for entity in entities:
        if not entity.functional_currency:
            missing.append(f"functional_currency:{entity.name}")
        if entity.ownership_pct is None:
            missing.append(f"ownership_pct:{entity.name}")

    mapping_file = _latest_file(db, engagement.id, FileType.COA_MAPPING.value)
    if not mapping_file:
        missing.append("coa_mapping_file")

    for entity in entities:
        tb_file = _latest_file(db, engagement.id, FileType.ENTITY_TB.value, entity_id=entity.id)
        gl_file = _latest_file(db, engagement.id, FileType.ENTITY_GL.value, entity_id=entity.id)
        if not (tb_file or gl_file):
            missing.append(f"source_file:{entity.name}")

    return len(missing) == 0, sorted(set(missing))


def _clear_run_state(db: Session, engagement_id: str) -> None:
    db.execute(delete(NormalizedBalance).where(NormalizedBalance.engagement_id == engagement_id))
    db.execute(delete(TranslatedBalance).where(TranslatedBalance.engagement_id == engagement_id))
    db.execute(delete(ConsolidationJournal).where(ConsolidationJournal.engagement_id == engagement_id))
    db.execute(delete(ControlException).where(ControlException.engagement_id == engagement_id))


def _load_normalized_data(db: Session, engagement: Engagement, entity: Entity) -> None:
    source = _latest_file(db, engagement.id, FileType.ENTITY_TB.value, entity_id=entity.id)
    if source is None:
        source = _latest_file(db, engagement.id, FileType.ENTITY_GL.value, entity_id=entity.id)
    if source is None:
        add_exception(
            db,
            engagement.id,
            "ENTITY_SOURCE_MISSING",
            f"No trial balance or GL file available for entity {entity.name}",
            blocking=True,
            entity_id=entity.id,
        )
        return

    rows, stats = parse_trial_balance(Path(source.storage_path), entity.functional_currency)
    for row in rows:
        db.add(
            NormalizedBalance(
                engagement_id=engagement.id,
                entity_id=entity.id,
                source_file_id=source.id,
                account_code=row["account_code"],
                account_name=row["account_name"],
                local_currency=row["local_currency"],
                period_amount=row["period_amount"],
                debit=row["debit"],
                credit=row["credit"],
                counterparty=row["counterparty"],
                is_intercompany=row["is_intercompany"],
                source_row_number=row["source_row_number"],
            )
        )

    if abs(Decimal(stats["imbalance"])) > Decimal("1"):
        add_exception(
            db,
            engagement.id,
            "TB_NOT_BALANCED",
            (
                f"Entity {entity.name} source file is not balanced. "
                f"Difference={stats['imbalance']}, Debit={stats['total_debit']}, Credit={stats['total_credit']}"
            ),
            blocking=True,
            entity_id=entity.id,
        )


def retrieve_fx_for_engagement(db: Session, engagement: Engagement) -> list[FXRate]:
    entities = [entity for entity in engagement.entities if entity.include_in_scope]
    for entity in entities:
        if not entity.functional_currency:
            add_exception(
                db,
                engagement.id,
                "ENTITY_CURRENCY_MISSING",
                f"Functional currency missing for {entity.name}",
                blocking=True,
                entity_id=entity.id,
            )
            continue
        try:
            store_standard_rates(db, engagement, entity)
        except FXServiceError as exc:
            add_exception(
                db,
                engagement.id,
                "FX_RETRIEVAL_FAILED",
                f"FX retrieval failed for {entity.name}: {exc}",
                blocking=True,
                entity_id=entity.id,
            )

    db.flush()
    return iter_fx_rows(db, engagement.id)


def process_engagement(db: Session, engagement: Engagement, actor: str = "system") -> tuple[str, int]:
    ready, missing = clarification_status(db, engagement)
    if not ready:
        engagement.status = EngagementStatus.CLARIFICATION_PENDING.value
        add_audit_event(
            db,
            "processing_blocked_missing_clarification",
            actor,
            {"missing": missing},
            engagement.id,
        )
        return (
            "Clarification stage incomplete. Provide all required fields/files before processing.",
            len(missing),
        )

    _clear_run_state(db, engagement.id)

    mapping_file = _latest_file(db, engagement.id, FileType.COA_MAPPING.value)
    if not mapping_file:
        add_exception(
            db,
            engagement.id,
            "MAPPING_FILE_MISSING",
            "Mapping file is required before processing",
            blocking=True,
        )
    else:
        try:
            import_mapping_file(db, engagement, Path(mapping_file.storage_path))
        except Exception as exc:
            add_exception(
                db,
                engagement.id,
                "MAPPING_IMPORT_FAILED",
                f"Unable to parse mapping file: {exc}",
                blocking=True,
            )

    entities = [entity for entity in engagement.entities if entity.include_in_scope]
    for entity in entities:
        try:
            _load_normalized_data(db, engagement, entity)
        except Exception as exc:
            add_exception(
                db,
                engagement.id,
                "NORMALIZATION_FAILED",
                f"Failed to normalize source for {entity.name}: {exc}",
                blocking=True,
                entity_id=entity.id,
            )

    retrieve_fx_for_engagement(db, engagement)

    from .translation_service import translate_entity

    for entity in entities:
        try:
            translate_entity(db, engagement, entity)
        except Exception as exc:
            add_exception(
                db,
                engagement.id,
                "TRANSLATION_FAILED",
                f"Failed FX translation for {entity.name}: {exc}",
                blocking=True,
                entity_id=entity.id,
            )

    consolidated = run_consolidation(db, engagement, entities)
    run_controls(db, engagement, consolidated)

    blocking_count = db.execute(
        select(func.count(ControlException.id)).where(
            and_(
                ControlException.engagement_id == engagement.id,
                ControlException.blocking.is_(True),
            )
        )
    ).scalar_one()

    generate_all_outputs(db, engagement.id, consolidated)

    if blocking_count > 0:
        engagement.status = EngagementStatus.BLOCKED.value
        add_audit_event(
            db,
            "processing_blocked_exceptions",
            actor,
            {"blocking_count": int(blocking_count)},
            engagement.id,
        )
        return (
            "Processing halted due to blocking exceptions. Review exception report and provide clarifications.",
            int(blocking_count),
        )

    engagement.status = EngagementStatus.PROCESSED.value
    add_audit_event(
        db,
        "processing_completed",
        actor,
        {"entities": len(entities), "outputs_generated": True},
        engagement.id,
    )
    return ("Consolidation completed successfully.", 0)
