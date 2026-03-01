from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EngagementCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class EngagementSummary(BaseModel):
    id: str
    name: str
    status: str
    presentation_currency: str
    reporting_period_start: date | None
    reporting_period_end: date | None
    average_method: str
    intercompany_method: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EntityCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    functional_currency: str = Field(min_length=3, max_length=3)
    ownership_pct: Decimal = Field(default=Decimal("1"), ge=Decimal("0"), le=Decimal("1"))
    has_nci: bool = False
    include_in_scope: bool = True
    intercompany_identifier: str | None = None

    @field_validator("functional_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ClarificationEntityItem(BaseModel):
    entity_id: str
    functional_currency: str = Field(min_length=3, max_length=3)
    ownership_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    has_nci: bool = False
    intercompany_identifier: str | None = None
    include_in_scope: bool = True

    @field_validator("functional_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ClarificationSubmission(BaseModel):
    reporting_period_start: date
    reporting_period_end: date
    presentation_currency: str = Field(default="USD", min_length=3, max_length=3)
    average_method: str = Field(default="DAY_WEIGHTED")
    intercompany_method: str = Field(default="ACCOUNT_TAG")
    entities: list[ClarificationEntityItem]

    @field_validator("presentation_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class ClarificationStatus(BaseModel):
    ready: bool
    missing_items: list[str]


class FXRateRow(BaseModel):
    entity_id: str
    entity_name: str
    base_currency: str
    quote_currency: str
    rate_type: str
    rate_date: date
    rate: Decimal
    source: str
    methodology: str
    missing_days: int
    is_override: bool


class FXOverrideRequest(BaseModel):
    entity_id: str
    rate_type: str
    rate_date: date
    rate: Decimal = Field(gt=Decimal("0"))
    note: str | None = None


class ProcessResponse(BaseModel):
    engagement_id: str
    status: str
    blocking_issues: int
    message: str


class ExceptionRow(BaseModel):
    id: int
    severity: str
    category: str
    message: str
    blocking: bool
    account_code: str | None
    entity_id: str | None
    status: str
    context_json: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactRow(BaseModel):
    id: str
    artifact_type: str
    file_path: str
    created_at: datetime

    model_config = {"from_attributes": True}
