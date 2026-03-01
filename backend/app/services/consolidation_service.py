from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..models import ConsolidationJournal, Entity, Engagement, JournalType, TranslatedBalance
from .common import add_exception


def _aggregate_translated(db: Session, engagement_id: str) -> dict[str, dict]:
    rows = db.execute(
        select(TranslatedBalance).where(TranslatedBalance.engagement_id == engagement_id)
    ).scalars().all()

    consolidated: dict[str, dict] = {}
    for row in rows:
        bucket = consolidated.setdefault(
            row.group_account_code,
            {
                "group_account_code": row.group_account_code,
                "group_account_name": row.group_account_name,
                "account_class": row.account_class,
                "usd_amount": Decimal("0"),
            },
        )
        bucket["usd_amount"] += Decimal(row.usd_amount)
    return consolidated


def _post_offset_journal(
    db: Session,
    engagement: Engagement,
    *,
    journal_type: str,
    account_code: str,
    account_class: str,
    description: str,
    adjustment: Decimal,
) -> None:
    if abs(adjustment) <= Decimal("0.0001"):
        return

    reserve_account = "ELIM-RESERVE"
    if account_class in {"REVENUE", "EXPENSE"}:
        reserve_account = "ELIM-PNL-RESERVE"

    if adjustment > 0:
        debit_account = account_code
        credit_account = reserve_account
    else:
        debit_account = reserve_account
        credit_account = account_code

    db.add(
        ConsolidationJournal(
            engagement_id=engagement.id,
            entity_id=None,
            journal_type=journal_type,
            description=description,
            debit_account=debit_account,
            credit_account=credit_account,
            amount_usd=abs(adjustment),
            source_reference="auto:consolidation",
            created_by="system",
        )
    )


def apply_intercompany_eliminations(
    db: Session,
    engagement: Engagement,
    consolidated: dict[str, dict],
) -> None:
    ic_rows = db.execute(
        select(TranslatedBalance).where(
            and_(
                TranslatedBalance.engagement_id == engagement.id,
                TranslatedBalance.is_intercompany.is_(True),
            )
        )
    ).scalars().all()

    if not ic_rows:
        return

    if not engagement.intercompany_method:
        add_exception(
            db,
            engagement.id,
            "INTERCOMPANY_METHOD_REQUIRED",
            "Intercompany balances exist but no intercompany elimination method is configured",
            blocking=True,
        )
        return

    method = engagement.intercompany_method.upper()
    if method not in {"ACCOUNT_TAG", "COUNTERPARTY_COLUMN", "NONE"}:
        add_exception(
            db,
            engagement.id,
            "INTERCOMPANY_METHOD_INVALID",
            f"Unsupported intercompany method '{engagement.intercompany_method}'",
            blocking=True,
        )
        return

    if method == "NONE":
        add_exception(
            db,
            engagement.id,
            "INTERCOMPANY_NOT_ELIMINATED",
            "Intercompany balances marked but method is NONE",
            severity="WARNING",
            blocking=False,
        )
        return

    grouped: defaultdict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for row in ic_rows:
        key = (row.group_account_code, row.account_class)
        if method == "COUNTERPARTY_COLUMN" and row.counterparty:
            key = (f"{row.group_account_code}::{row.counterparty}", row.account_class)
        grouped[key] += Decimal(row.usd_amount)

    for key, net in grouped.items():
        account_key, account_class = key
        account_code = account_key.split("::", 1)[0]
        if abs(net) <= Decimal("0.0001"):
            continue

        adjustment = -net
        if account_code not in consolidated:
            consolidated[account_code] = {
                "group_account_code": account_code,
                "group_account_name": account_code,
                "account_class": account_class,
                "usd_amount": Decimal("0"),
            }

        consolidated[account_code]["usd_amount"] += adjustment

        journal_type = JournalType.INTERCOMPANY_ELIM.value
        if account_class in {"REVENUE", "EXPENSE"}:
            journal_type = JournalType.REVENUE_COST_ELIM.value

        _post_offset_journal(
            db,
            engagement,
            journal_type=journal_type,
            account_code=account_code,
            account_class=account_class,
            description=f"Auto intercompany elimination ({method}) for {account_code}",
            adjustment=adjustment,
        )


def apply_nci(db: Session, engagement: Engagement, consolidated: dict[str, dict], entities: list[Entity]) -> None:
    for entity in entities:
        if not entity.include_in_scope:
            continue
        if not entity.has_nci:
            continue

        ownership = Decimal(entity.ownership_pct)
        if ownership >= Decimal("1"):
            continue

        nci_pct = Decimal("1") - ownership
        rows = db.execute(
            select(TranslatedBalance).where(
                and_(
                    TranslatedBalance.engagement_id == engagement.id,
                    TranslatedBalance.entity_id == entity.id,
                )
            )
        ).scalars().all()
        if not rows:
            continue

        equity_base = sum(
            (Decimal(r.usd_amount) for r in rows if r.account_class == "EQUITY"),
            start=Decimal("0"),
        )

        pnl_sum = sum(
            (Decimal(r.usd_amount) for r in rows if r.account_class in {"REVENUE", "EXPENSE"}),
            start=Decimal("0"),
        )
        net_profit = -pnl_sum

        nci_equity = (equity_base * nci_pct).quantize(Decimal("0.000001"))
        nci_profit = (net_profit * nci_pct).quantize(Decimal("0.000001"))

        if abs(nci_equity) > Decimal("0.0001"):
            code = "NCI-EQUITY"
            consolidated.setdefault(
                code,
                {
                    "group_account_code": code,
                    "group_account_name": "Non-controlling interests",
                    "account_class": "EQUITY",
                    "usd_amount": Decimal("0"),
                },
            )
            consolidated[code]["usd_amount"] += nci_equity
            _post_offset_journal(
                db,
                engagement,
                journal_type=JournalType.NCI.value,
                account_code=code,
                account_class="EQUITY",
                description=f"NCI equity allocation for {entity.name}",
                adjustment=nci_equity,
            )

        if abs(nci_profit) > Decimal("0.0001"):
            code = "NCI-PROFIT"
            consolidated.setdefault(
                code,
                {
                    "group_account_code": code,
                    "group_account_name": "Profit attributable to NCI",
                    "account_class": "EXPENSE",
                    "usd_amount": Decimal("0"),
                },
            )
            consolidated[code]["usd_amount"] += nci_profit
            _post_offset_journal(
                db,
                engagement,
                journal_type=JournalType.NCI.value,
                account_code=code,
                account_class="EXPENSE",
                description=f"NCI profit allocation for {entity.name}",
                adjustment=nci_profit,
            )


def run_consolidation(db: Session, engagement: Engagement, entities: list[Entity]) -> list[dict]:
    consolidated = _aggregate_translated(db, engagement.id)
    apply_intercompany_eliminations(db, engagement, consolidated)
    apply_nci(db, engagement, consolidated, entities)

    result = list(consolidated.values())
    result.sort(key=lambda row: row["group_account_code"])
    return result
