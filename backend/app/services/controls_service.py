from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ConsolidationJournal, ControlException, Engagement, JournalType, TranslatedBalance
from .common import add_exception


def run_controls(db: Session, engagement: Engagement, consolidated_rows: list[dict]) -> dict[str, int]:
    blocking = 0
    warnings = 0

    total_sum = sum((Decimal(str(row["usd_amount"])) for row in consolidated_rows), start=Decimal("0"))
    if abs(total_sum) > Decimal("0.50"):
        add_exception(
            db,
            engagement.id,
            "DEBITS_CREDITS_OUT_OF_BALANCE",
            f"Consolidated trial balance does not net to zero (difference: {total_sum})",
            blocking=True,
        )
        blocking += 1

    cta_journal_total = db.execute(
        select(func.coalesce(func.sum(ConsolidationJournal.amount_usd), 0)).where(
            and_(
                ConsolidationJournal.engagement_id == engagement.id,
                ConsolidationJournal.journal_type == JournalType.TRANSLATION_CTA.value,
            )
        )
    ).scalar_one()
    cta_tb_total = Decimal("0")
    for row in consolidated_rows:
        if row["group_account_code"] == settings.cta_account_code:
            cta_tb_total += Decimal(str(row["usd_amount"]))

    if abs(Decimal(cta_journal_total) - abs(cta_tb_total)) > Decimal("1"):
        add_exception(
            db,
            engagement.id,
            "CTA_RECONCILIATION_FAILED",
            (
                "CTA in trial balance does not reconcile to CTA journals "
                f"(TB={cta_tb_total}, journals={cta_journal_total})"
            ),
            blocking=True,
        )
        blocking += 1

    # Retained earnings movement check if expected accounts are mapped in the output.
    by_code = {row["group_account_code"]: Decimal(str(row["usd_amount"])) for row in consolidated_rows}
    if {"RETAINED-EARNINGS-OPEN", "RETAINED-EARNINGS-CLOSE", "PROFIT-LOSS"}.issubset(by_code):
        expected_close = by_code["RETAINED-EARNINGS-OPEN"] + by_code["PROFIT-LOSS"]
        actual_close = by_code["RETAINED-EARNINGS-CLOSE"]
        if abs(expected_close - actual_close) > Decimal("1"):
            add_exception(
                db,
                engagement.id,
                "RETAINED_EARNINGS_MOVEMENT_FAILED",
                (
                    "Retained earnings movement mismatch "
                    f"(expected close {expected_close}, actual close {actual_close})"
                ),
                blocking=True,
            )
            blocking += 1
    else:
        add_exception(
            db,
            engagement.id,
            "RETAINED_EARNINGS_CHECK_SKIPPED",
            "Retained earnings movement check skipped because required tagged accounts are missing",
            severity="WARNING",
            blocking=False,
        )
        warnings += 1

    # Unusual variance check by entity/account using median-based threshold.
    entity_account = db.execute(
        select(
            TranslatedBalance.group_account_code,
            TranslatedBalance.entity_id,
            func.sum(TranslatedBalance.usd_amount),
        )
        .where(TranslatedBalance.engagement_id == engagement.id)
        .group_by(TranslatedBalance.group_account_code, TranslatedBalance.entity_id)
    ).all()

    by_account: defaultdict[str, list[Decimal]] = defaultdict(list)
    for account_code, _, amount in entity_account:
        by_account[account_code].append(abs(Decimal(amount)))

    for account_code, amounts in by_account.items():
        if len(amounts) < 3:
            continue
        med = Decimal(str(median([float(value) for value in amounts])))
        if med <= Decimal("0"):
            continue

        threshold = med * Decimal("5")
        for amount in amounts:
            if amount > threshold and amount > Decimal("10000"):
                add_exception(
                    db,
                    engagement.id,
                    "UNUSUAL_VARIANCE",
                    f"Unusual variance detected on account {account_code}: {amount} exceeds threshold {threshold}",
                    severity="WARNING",
                    blocking=False,
                    account_code=account_code,
                )
                warnings += 1
                break

    return {"blocking": blocking, "warnings": warnings}
