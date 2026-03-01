from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent, ControlException, ExceptionSeverity


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return Decimal(text)
    except Exception:
        return default


def add_exception(
    db: Session,
    engagement_id: str,
    category: str,
    message: str,
    *,
    severity: str = ExceptionSeverity.ERROR.value,
    blocking: bool = False,
    entity_id: str | None = None,
    account_code: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    row = ControlException(
        engagement_id=engagement_id,
        entity_id=entity_id,
        severity=severity,
        category=category,
        message=message,
        blocking=blocking,
        account_code=account_code,
        context_json=context,
    )
    db.add(row)


def add_audit_event(
    db: Session,
    event_type: str,
    actor: str,
    payload: dict[str, Any] | None = None,
    engagement_id: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            engagement_id=engagement_id,
            event_type=event_type,
            actor=actor,
            payload_json=payload,
            created_at=datetime.now(timezone.utc),
        )
    )
