from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class EngagementStatus(str, Enum):
    DRAFT = "DRAFT"
    CLARIFICATION_PENDING = "CLARIFICATION_PENDING"
    READY_TO_PROCESS = "READY_TO_PROCESS"
    PROCESSED = "PROCESSED"
    BLOCKED = "BLOCKED"


class FileType(str, Enum):
    ENTITY_TB = "ENTITY_TB"
    ENTITY_GL = "ENTITY_GL"
    CONSOLIDATION_TEMPLATE = "CONSOLIDATION_TEMPLATE"
    COA_MAPPING = "COA_MAPPING"


class TranslationPolicy(str, Enum):
    CLOSING = "CLOSING"
    AVERAGE = "AVERAGE"
    HISTORICAL = "HISTORICAL"


class AccountClass(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class RateType(str, Enum):
    CLOSING = "CLOSING"
    AVERAGE = "AVERAGE"
    HISTORICAL = "HISTORICAL"


class ExceptionSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ExceptionStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class JournalType(str, Enum):
    TRANSLATION_CTA = "TRANSLATION_CTA"
    INTERCOMPANY_ELIM = "INTERCOMPANY_ELIM"
    REVENUE_COST_ELIM = "REVENUE_COST_ELIM"
    NCI = "NCI"
    MANUAL = "MANUAL"


class ArtifactType(str, Enum):
    CONSOLIDATED_TB = "CONSOLIDATED_TB"
    INCOME_STATEMENT = "INCOME_STATEMENT"
    BALANCE_SHEET = "BALANCE_SHEET"
    JOURNAL_LOG = "JOURNAL_LOG"
    FX_REPORT = "FX_REPORT"
    EXCEPTION_REPORT = "EXCEPTION_REPORT"
    REPORTING_PACK = "REPORTING_PACK"


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=EngagementStatus.DRAFT.value, nullable=False)
    presentation_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    reporting_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    reporting_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    average_method: Mapped[str] = mapped_column(String(32), default="DAY_WEIGHTED", nullable=False)
    intercompany_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    entities: Mapped[list[Entity]] = relationship(back_populates="engagement", cascade="all, delete-orphan")
    files: Mapped[list[UploadedFile]] = relationship(back_populates="engagement", cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    functional_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    ownership_pct: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=Decimal("1.0000"), nullable=False)
    has_nci: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    include_in_scope: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    intercompany_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    engagement: Mapped[Engagement] = relationship(back_populates="entities")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=True)
    file_type: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    engagement: Mapped[Engagement] = relationship(back_populates="files")


class ClarificationItem(Base):
    __tablename__ = "clarification_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_clarification_engagement_key", "engagement_id", "key", unique=True),
    )


class COAMapping(Base):
    __tablename__ = "coa_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=True)
    local_account_code: Mapped[str] = mapped_column(String(128), nullable=False)
    local_account_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    group_account_code: Mapped[str] = mapped_column(String(128), nullable=False)
    group_account_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    account_class: Mapped[str] = mapped_column(String(32), nullable=False)
    translation_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    historical_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_intercompany: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class NormalizedBalance(Base):
    __tablename__ = "normalized_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(128), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    local_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    debit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    credit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_intercompany: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FXRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    methodology: Mapped[str] = mapped_column(String(255), nullable=False)
    missing_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_fx_rates_lookup", "engagement_id", "entity_id", "rate_type", "rate_date"),
    )


class TranslatedBalance(Base):
    __tablename__ = "translated_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    group_account_code: Mapped[str] = mapped_column(String(128), nullable=False)
    group_account_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    account_class: Mapped[str] = mapped_column(String(32), nullable=False)
    translation_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    local_account_code: Mapped[str] = mapped_column(String(128), nullable=False)
    local_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    local_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fx_rate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    usd_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    is_intercompany: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ConsolidationJournal(Base):
    __tablename__ = "consolidation_journals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=True)
    journal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    debit_account: Mapped[str] = mapped_column(String(128), nullable=False)
    credit_account: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ControlException(Base):
    __tablename__ = "control_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    account_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ExceptionStatus.OPEN.value, nullable=False)
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class OutputArtifact(Base):
    __tablename__ = "output_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engagement_id: Mapped[str | None] = mapped_column(ForeignKey("engagements.id", ondelete="CASCADE"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
