from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable

import httpx
from sqlalchemy import and_, delete, desc, select
from sqlalchemy.orm import Session

from ..models import Entity, Engagement, FXRate, RateType

FRANKFURTER_SOURCE = "Frankfurter (ECB reference rates)"
FRANKFURTER_URL = "https://api.frankfurter.app"


class FXServiceError(RuntimeError):
    pass


def _parse_series(payload: dict, quote_currency: str) -> "OrderedDict[date, Decimal]":
    out: "OrderedDict[date, Decimal]" = OrderedDict()
    rates = payload.get("rates", {})
    for key in sorted(rates.keys()):
        value = rates[key]
        if isinstance(value, dict):
            value = value.get(quote_currency)
        if value is None:
            continue
        out[date.fromisoformat(key)] = Decimal(str(value))
    return out


def fetch_daily_series(base_currency: str, quote_currency: str, start: date, end: date) -> "OrderedDict[date, Decimal]":
    if base_currency == quote_currency:
        return OrderedDict({start: Decimal("1"), end: Decimal("1")})

    url = (
        f"{FRANKFURTER_URL}/{start.isoformat()}..{end.isoformat()}"
        f"?from={base_currency}&to={quote_currency}"
    )
    try:
        response = httpx.get(url, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        raise FXServiceError(f"Unable to retrieve FX rates from source: {exc}") from exc

    series = _parse_series(response.json(), quote_currency)
    if not series:
        raise FXServiceError(
            f"No FX data returned for {base_currency}/{quote_currency} between {start} and {end}"
        )
    return series


def _latest_on_or_before(series: "OrderedDict[date, Decimal]", target: date) -> tuple[date, Decimal]:
    valid = [(d, r) for d, r in series.items() if d <= target]
    if not valid:
        raise FXServiceError(f"No FX rate available on or before {target}")
    return valid[-1]


def closing_rate(series: "OrderedDict[date, Decimal]", period_end: date) -> tuple[date, Decimal, int]:
    rate_date, rate = _latest_on_or_before(series, period_end)
    missing_days = max((period_end - rate_date).days, 0)
    return rate_date, rate, missing_days


def day_weighted_average(series: "OrderedDict[date, Decimal]", period_start: date, period_end: date) -> tuple[Decimal, int]:
    ordered_items = list(series.items())
    missing_days = 0
    running_total = Decimal("0")
    day_count = 0

    current = period_start
    while current <= period_end:
        applicable_rate = None
        for d, r in ordered_items:
            if d <= current:
                applicable_rate = r
            else:
                break

        if applicable_rate is None:
            missing_days += 1
            # Conservative fallback: use earliest available rate if period starts before first quote.
            applicable_rate = ordered_items[0][1]
        elif current not in series:
            missing_days += 1

        running_total += applicable_rate
        day_count += 1
        current += timedelta(days=1)

    if day_count == 0:
        raise FXServiceError("Cannot calculate average rate for empty period")

    avg = running_total / Decimal(str(day_count))
    return avg.quantize(Decimal("0.00000001")), missing_days


def store_standard_rates(db: Session, engagement: Engagement, entity: Entity) -> list[FXRate]:
    if not engagement.reporting_period_start or not engagement.reporting_period_end:
        raise FXServiceError("Reporting period is required before FX retrieval")

    db.execute(
        delete(FXRate).where(
            and_(
                FXRate.engagement_id == engagement.id,
                FXRate.entity_id == entity.id,
                FXRate.rate_type.in_([RateType.CLOSING.value, RateType.AVERAGE.value]),
                FXRate.is_override.is_(False),
            )
        )
    )

    if entity.functional_currency == engagement.presentation_currency:
        closing = FXRate(
            engagement_id=engagement.id,
            entity_id=entity.id,
            source="Internal",
            base_currency=entity.functional_currency,
            quote_currency=engagement.presentation_currency,
            rate_type=RateType.CLOSING.value,
            rate_date=engagement.reporting_period_end,
            rate=Decimal("1"),
            methodology="Identity rate",
            missing_days=0,
            is_override=False,
        )
        avg = FXRate(
            engagement_id=engagement.id,
            entity_id=entity.id,
            source="Internal",
            base_currency=entity.functional_currency,
            quote_currency=engagement.presentation_currency,
            rate_type=RateType.AVERAGE.value,
            rate_date=engagement.reporting_period_end,
            rate=Decimal("1"),
            methodology="Identity rate",
            missing_days=0,
            is_override=False,
        )
        db.add_all([closing, avg])
        return [closing, avg]

    series = fetch_daily_series(
        entity.functional_currency,
        engagement.presentation_currency,
        engagement.reporting_period_start,
        engagement.reporting_period_end,
    )
    close_date, close_rate, closing_missing = closing_rate(series, engagement.reporting_period_end)
    avg_rate, average_missing = day_weighted_average(
        series,
        engagement.reporting_period_start,
        engagement.reporting_period_end,
    )

    closing_row = FXRate(
        engagement_id=engagement.id,
        entity_id=entity.id,
        source=FRANKFURTER_SOURCE,
        base_currency=entity.functional_currency,
        quote_currency=engagement.presentation_currency,
        rate_type=RateType.CLOSING.value,
        rate_date=close_date,
        rate=close_rate,
        methodology="Closing spot rate as at reporting date (or latest prior business day)",
        missing_days=closing_missing,
        is_override=False,
    )
    average_row = FXRate(
        engagement_id=engagement.id,
        entity_id=entity.id,
        source=FRANKFURTER_SOURCE,
        base_currency=entity.functional_currency,
        quote_currency=engagement.presentation_currency,
        rate_type=RateType.AVERAGE.value,
        rate_date=engagement.reporting_period_end,
        rate=avg_rate,
        methodology="Day-weighted daily average with non-quote days forward-filled",
        missing_days=average_missing,
        is_override=False,
    )
    db.add_all([closing_row, average_row])
    return [closing_row, average_row]


def get_latest_rate(db: Session, engagement_id: str, entity_id: str, rate_type: str) -> FXRate | None:
    stmt = (
        select(FXRate)
        .where(
            and_(
                FXRate.engagement_id == engagement_id,
                FXRate.entity_id == entity_id,
                FXRate.rate_type == rate_type,
            )
        )
        .order_by(desc(FXRate.is_override), desc(FXRate.rate_date), desc(FXRate.id))
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def fetch_historical_rate(
    db: Session,
    engagement: Engagement,
    entity: Entity,
    historical_date: date,
) -> FXRate:
    if entity.functional_currency == engagement.presentation_currency:
        row = FXRate(
            engagement_id=engagement.id,
            entity_id=entity.id,
            source="Internal",
            base_currency=entity.functional_currency,
            quote_currency=engagement.presentation_currency,
            rate_type=RateType.HISTORICAL.value,
            rate_date=historical_date,
            rate=Decimal("1"),
            methodology="Identity rate",
            missing_days=0,
            is_override=False,
        )
        db.add(row)
        return row

    range_start = historical_date - timedelta(days=10)
    series = fetch_daily_series(
        entity.functional_currency,
        engagement.presentation_currency,
        range_start,
        historical_date,
    )
    rate_date, rate = _latest_on_or_before(series, historical_date)
    missing_days = max((historical_date - rate_date).days, 0)
    row = FXRate(
        engagement_id=engagement.id,
        entity_id=entity.id,
        source=FRANKFURTER_SOURCE,
        base_currency=entity.functional_currency,
        quote_currency=engagement.presentation_currency,
        rate_type=RateType.HISTORICAL.value,
        rate_date=rate_date,
        rate=rate,
        methodology="Historical spot rate for equity translation",
        missing_days=missing_days,
        is_override=False,
    )
    db.add(row)
    return row


def get_or_fetch_historical_rate(
    db: Session,
    engagement: Engagement,
    entity: Entity,
    historical_date: date,
) -> FXRate:
    override_stmt = (
        select(FXRate)
        .where(
            and_(
                FXRate.engagement_id == engagement.id,
                FXRate.entity_id == entity.id,
                FXRate.rate_type == RateType.HISTORICAL.value,
                FXRate.is_override.is_(True),
                FXRate.rate_date == historical_date,
            )
        )
        .order_by(desc(FXRate.id))
        .limit(1)
    )
    override = db.execute(override_stmt).scalar_one_or_none()
    if override:
        return override

    cached_stmt = (
        select(FXRate)
        .where(
            and_(
                FXRate.engagement_id == engagement.id,
                FXRate.entity_id == entity.id,
                FXRate.rate_type == RateType.HISTORICAL.value,
                FXRate.rate_date <= historical_date,
            )
        )
        .order_by(desc(FXRate.rate_date), desc(FXRate.id))
        .limit(1)
    )
    cached = db.execute(cached_stmt).scalar_one_or_none()
    if cached:
        return cached

    return fetch_historical_rate(db, engagement, entity, historical_date)


def iter_fx_rows(db: Session, engagement_id: str) -> list[FXRate]:
    stmt = (
        select(FXRate)
        .where(FXRate.engagement_id == engagement_id)
        .order_by(FXRate.entity_id, FXRate.rate_type, desc(FXRate.is_override), desc(FXRate.rate_date))
    )
    return list(db.execute(stmt).scalars().all())
