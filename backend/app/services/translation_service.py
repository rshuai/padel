from __future__ import annotations

from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    COAMapping,
    ConsolidationJournal,
    Entity,
    Engagement,
    JournalType,
    NormalizedBalance,
    RateType,
    TranslationPolicy,
    TranslatedBalance,
)
from .common import add_exception
from .fx_service import get_latest_rate, get_or_fetch_historical_rate


def _mapping_by_local_code(db: Session, engagement_id: str, entity_id: str) -> dict[str, COAMapping]:
    entity_specific = db.execute(
        select(COAMapping).where(
            and_(
                COAMapping.engagement_id == engagement_id,
                COAMapping.entity_id == entity_id,
            )
        )
    ).scalars().all()

    global_rows = db.execute(
        select(COAMapping).where(
            and_(
                COAMapping.engagement_id == engagement_id,
                COAMapping.entity_id.is_(None),
            )
        )
    ).scalars().all()

    result: dict[str, COAMapping] = {row.local_account_code: row for row in global_rows}
    for row in entity_specific:
        result[row.local_account_code] = row
    return result


def _pick_rate(
    db: Session,
    engagement: Engagement,
    entity: Entity,
    mapping: COAMapping,
):
    policy = mapping.translation_policy
    if policy == TranslationPolicy.CLOSING.value:
        rate_row = get_latest_rate(db, engagement.id, entity.id, RateType.CLOSING.value)
        if not rate_row:
            add_exception(
                db,
                engagement.id,
                "FX_RATE_MISSING",
                f"Closing rate missing for entity {entity.name}",
                blocking=True,
                entity_id=entity.id,
                account_code=mapping.local_account_code,
            )
            return None
        return rate_row

    if policy == TranslationPolicy.AVERAGE.value:
        rate_row = get_latest_rate(db, engagement.id, entity.id, RateType.AVERAGE.value)
        if not rate_row:
            add_exception(
                db,
                engagement.id,
                "FX_RATE_MISSING",
                f"Average rate missing for entity {entity.name}",
                blocking=True,
                entity_id=entity.id,
                account_code=mapping.local_account_code,
            )
            return None
        return rate_row

    if policy == TranslationPolicy.HISTORICAL.value:
        if not mapping.historical_rate_date:
            add_exception(
                db,
                engagement.id,
                "HISTORICAL_RATE_DATE_REQUIRED",
                (
                    f"Historical rate policy requires a historical rate date for local account "
                    f"{mapping.local_account_code}"
                ),
                blocking=True,
                entity_id=entity.id,
                account_code=mapping.local_account_code,
            )
            return None
        return get_or_fetch_historical_rate(db, engagement, entity, mapping.historical_rate_date)

    add_exception(
        db,
        engagement.id,
        "UNKNOWN_TRANSLATION_POLICY",
        f"Unsupported translation policy {policy} for account {mapping.local_account_code}",
        blocking=True,
        entity_id=entity.id,
        account_code=mapping.local_account_code,
    )
    return None


def translate_entity(db: Session, engagement: Engagement, entity: Entity) -> dict[str, Decimal]:
    mapping_lookup = _mapping_by_local_code(db, engagement.id, entity.id)

    rows = db.execute(
        select(NormalizedBalance).where(
            and_(
                NormalizedBalance.engagement_id == engagement.id,
                NormalizedBalance.entity_id == entity.id,
            )
        )
    ).scalars().all()

    translated_count = 0
    local_total = Decimal("0")
    usd_total = Decimal("0")

    for row in rows:
        mapping = mapping_lookup.get(row.account_code)
        if not mapping:
            add_exception(
                db,
                engagement.id,
                "UNMAPPED_ACCOUNT",
                f"Local account {row.account_code} has no group mapping",
                blocking=True,
                entity_id=entity.id,
                account_code=row.account_code,
            )
            continue

        rate_row = _pick_rate(db, engagement, entity, mapping)
        if not rate_row:
            continue

        usd_amount = (Decimal(row.period_amount) * Decimal(rate_row.rate)).quantize(Decimal("0.000001"))
        db.add(
            TranslatedBalance(
                engagement_id=engagement.id,
                entity_id=entity.id,
                group_account_code=mapping.group_account_code,
                group_account_name=mapping.group_account_name,
                account_class=mapping.account_class,
                translation_policy=mapping.translation_policy,
                local_account_code=row.account_code,
                local_currency=row.local_currency,
                local_amount=row.period_amount,
                fx_rate=rate_row.rate,
                fx_rate_type=rate_row.rate_type,
                fx_rate_date=rate_row.rate_date,
                usd_amount=usd_amount,
                is_intercompany=bool(mapping.is_intercompany or row.is_intercompany),
                counterparty=row.counterparty,
            )
        )
        translated_count += 1
        local_total += Decimal(row.period_amount)
        usd_total += usd_amount

    cta_amount = (-usd_total).quantize(Decimal("0.000001"))
    if abs(cta_amount) > Decimal("0.0001"):
        db.add(
            TranslatedBalance(
                engagement_id=engagement.id,
                entity_id=entity.id,
                group_account_code=settings.cta_account_code,
                group_account_name=settings.cta_account_name,
                account_class="EQUITY",
                translation_policy=TranslationPolicy.CLOSING.value,
                local_account_code="CTA_SYSTEM",
                local_currency=engagement.presentation_currency,
                local_amount=Decimal("0"),
                fx_rate=Decimal("1"),
                fx_rate_type=RateType.CLOSING.value,
                fx_rate_date=engagement.reporting_period_end,
                usd_amount=cta_amount,
                is_intercompany=False,
                counterparty=None,
            )
        )

        if cta_amount > 0:
            debit_account = settings.cta_account_code
            credit_account = "FX-TRANSLATION-RESERVE"
        else:
            debit_account = "FX-TRANSLATION-RESERVE"
            credit_account = settings.cta_account_code

        db.add(
            ConsolidationJournal(
                engagement_id=engagement.id,
                entity_id=entity.id,
                journal_type=JournalType.TRANSLATION_CTA.value,
                description=f"CTA balancing for entity {entity.name}",
                debit_account=debit_account,
                credit_account=credit_account,
                amount_usd=abs(cta_amount),
                source_reference="auto:translation",
                created_by="system",
            )
        )

    return {
        "translated_rows": Decimal(str(translated_count)),
        "local_total": local_total,
        "usd_total_before_cta": usd_total,
        "cta": cta_amount,
    }
