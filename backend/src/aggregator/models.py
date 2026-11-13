"""Служебные таблицы сборщика/агрегатора.

Отделены от доменных моделей (src/models): здесь хранится состояние сбора и
обработки, а не то, что видит бэк. Состояние сбора и состояние обработки —
разные вещи (см. ТЗ): сбой классификации или S3 не должен блокировать
сохранение следующих публикаций, поэтому каждый этап публикации хранится как
отдельная задача в agg_processing_tasks.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base, enum_check


class RawItemKind(StrEnum):
    TELEGRAM_POST = "telegram_post"
    FARPOST_LISTING = "farpost_listing"
    FISHING_VL_SPOT = "fishing_vl_spot"


class ProcessingStage(StrEnum):
    NORMALIZE = "normalize"
    CLASSIFY = "classify"
    RESOLVE = "resolve"
    DEDUP = "dedup"
    MEDIA = "media"
    PUBLISH = "publish"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class CursorType(StrEnum):
    INCREMENTAL = "incremental"
    BACKFILL = "backfill"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class DedupDecisionKind(StrEnum):
    DUPLICATE = "duplicate"
    DISTINCT = "distinct"
    UNCERTAIN = "uncertain"


class CandidateKind(StrEnum):
    SPECIES = "species"
    SPOT = "spot"
    METHOD = "method"


class AttachmentDownloadState(StrEnum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    UPLOADED = "uploaded"
    FAILED = "failed"


class AggRawItem(Base):
    """Сырая публикация/карточка источника. Один раз получена — хранится
    всегда, независимо от последующих решений классификатора."""

    __tablename__ = "agg_raw_items"
    __table_args__ = (
        enum_check("kind", RawItemKind),
        UniqueConstraint("source_key", "external_id", name="uq_source_external"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    source_key: Mapped[str] = mapped_column(String(100), index=True)
    """Строковый идентификатор источника: 'telegram:<external_id сущности sources>'
    или 'farpost' или 'fishing_vl'. Не у всех источников есть запись в sources
    (Фарпост и fishing-vl.ru туда не пишутся согласно модели PDF)."""
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(50))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Проставляется только по достоверному событию удаления, не по пробелу
    в последовательности ID."""

    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="SET NULL"), index=True
    )
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("listings.id", ondelete="SET NULL"), index=True
    )
    spot_id: Mapped[int | None] = mapped_column(
        ForeignKey("spots.id", ondelete="SET NULL"), index=True
    )

    versions: Mapped[list["AggContentVersion"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AggContentVersion.version_no",
    )


class AggContentVersion(Base):
    """Версия содержимого: исходный и очищенный текст. Новая версия
    появляется при редактировании публикации источником или смене правил
    нормализации. Исходный текст никогда не перезаписывается."""

    __tablename__ = "agg_content_versions"
    __table_args__ = (
        UniqueConstraint("raw_item_id", "version_no"),
        Index(
            "ix_agg_content_versions_normalized_text_trgm",
            "normalized_text",
            postgresql_using="gin",
            postgresql_ops={"normalized_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        ForeignKey("agg_raw_items.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int] = mapped_column(SmallInteger)
    original_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    removed_boilerplate: Mapped[str | None] = mapped_column(Text)
    """Распознанный служебный хвост (ссылки/призыв прислать отчёт), убранный
    из normalized_text, но сохранённый отдельно для диагностики."""
    normalization_version: Mapped[str] = mapped_column(String(50))
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AggCursor(Base):
    """Курсор обхода источника. Курсор новых сообщений и курсор загрузки
    истории хранятся раздельно по cursor_type."""

    __tablename__ = "agg_cursors"
    __table_args__ = (
        enum_check("cursor_type", CursorType),
        UniqueConstraint("source_key", "cursor_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), index=True)
    cursor_type: Mapped[str] = mapped_column(String(20))
    position: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AggRun(Base):
    """История запусков команд сборщика с метриками по источнику."""

    __tablename__ = "agg_runs"
    __table_args__ = (enum_check("status", RunStatus),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), index=True)
    command: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), server_default=sql_text("'running'"))
    stats: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AggClassification(Base):
    """Результат DeepSeek, закешированный по версии содержимого, версии
    инструкции и модели: смена промпта должна позволять осознанный
    пересчёт, не затрагивая остальные кеш-ключи."""

    __tablename__ = "agg_classifications"
    __table_args__ = (
        UniqueConstraint(
            "content_version_id", "model", "prompt_version", name="uq_cache_key"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    content_version_id: Mapped[int] = mapped_column(
        ForeignKey("agg_content_versions.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    decision: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSONB)
    """Полный ответ классификатора по контракту (decision/category/reason/
    extracted fields/evidence)."""
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Numeric(10, 5))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AggProcessingTask(Base):
    """Очередь задач по этапам. Статус per-stage, чтобы сбой одного этапа
    (например DeepSeek) не блокировал сохранение следующих сырых публикаций
    и позволял ручной повтор (retry-failed)."""

    __tablename__ = "agg_processing_tasks"
    __table_args__ = (
        enum_check("stage", ProcessingStage),
        enum_check("status", TaskStatus),
        UniqueConstraint("raw_item_id", "stage"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        ForeignKey("agg_raw_items.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default=sql_text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    """Когда задача снова доступна к выполнению (экспоненциальный backoff)."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AggMediaAttachment(Base):
    """Вложение сырой публикации до и после загрузки в S3. Хранит
    стабильную ссылку на источник вложения (file_id Telegram, id фото
    Фарпоста), так как прямые URL источника могут истекать."""

    __tablename__ = "agg_media_attachments"
    __table_args__ = (
        enum_check("download_state", AttachmentDownloadState),
        UniqueConstraint("raw_item_id", "attachment_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        ForeignKey("agg_raw_items.id", ondelete="CASCADE"), index=True
    )
    attachment_index: Mapped[int] = mapped_column(SmallInteger)
    source_ref: Mapped[str] = mapped_column(Text)
    """Стабильный идентификатор источника вложения (не временный URL)."""
    media_type: Mapped[str] = mapped_column(String(10))
    download_state: Mapped[str] = mapped_column(
        String(20), server_default=sql_text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(Integer, server_default=sql_text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    media_file_id: Mapped[int | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), index=True
    )


class AggDedupDecision(Base):
    """Решение по паре потенциальных дублей с признаками и версией
    алгоритма — обратимо, не объединяет кластер автоматически."""

    __tablename__ = "agg_dedup_decisions"
    __table_args__ = (enum_check("decision", DedupDecisionKind),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_a_id: Mapped[int] = mapped_column(
        ForeignKey("agg_raw_items.id", ondelete="CASCADE"), index=True
    )
    item_b_id: Mapped[int] = mapped_column(
        ForeignKey("agg_raw_items.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[int] = mapped_column(SmallInteger)
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    features: Mapped[dict | None] = mapped_column(JSONB)
    algorithm_version: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AggUnresolvedCandidate(Base):
    """Неразрешённое название вида/места/способа — кандидат для ручной
    модерации, без создания фиктивных справочных записей."""

    __tablename__ = "agg_unresolved_candidates"
    __table_args__ = (enum_check("kind", CandidateKind),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_item_id: Mapped[int] = mapped_column(
        ForeignKey("agg_raw_items.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    raw_name: Mapped[str] = mapped_column(String(255))
    evidence: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, server_default=sql_text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
