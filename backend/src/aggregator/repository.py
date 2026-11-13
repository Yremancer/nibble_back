
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import (
    AggClassification,
    AggContentVersion,
    AggCursor,
    AggMediaAttachment,
    AggProcessingTask,
    AggRawItem,
    AggRun,
    AggUnresolvedCandidate,
    ProcessingStage,
    TaskStatus,
)


class RawItemRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_source_external(
        self, source_key: str, external_id: str
    ) -> AggRawItem | None:
        result = await self._session.execute(
            select(AggRawItem).where(
                AggRawItem.source_key == source_key,
                AggRawItem.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_raw_item(
        self,
        *,
        kind: str,
        source_key: str,
        external_id: str,
        raw_payload: dict,
        content_hash: str,
        parser_version: str,
    ) -> tuple[AggRawItem, bool, bool]:
        existing = await self.get_by_source_external(source_key, external_id)
        now = datetime.now(timezone.utc)

        if existing is None:
            item = AggRawItem(
                kind=kind,
                source_key=source_key,
                external_id=external_id,
                raw_payload=raw_payload,
                content_hash=content_hash,
                parser_version=parser_version,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
            )
            self._session.add(item)
            await self._session.flush()
            return item, True, True

        existing.last_seen_at = now
        content_changed = existing.content_hash != content_hash
        if content_changed:
            existing.raw_payload = raw_payload
            existing.content_hash = content_hash
            existing.parser_version = parser_version
            existing.last_changed_at = now
        await self._session.flush()
        return existing, content_changed, False

    async def add_content_version(
        self,
        raw_item_id: int,
        *,
        original_text: str | None,
        normalized_text: str | None,
        removed_boilerplate: str | None,
        normalization_version: str,
    ) -> AggContentVersion:
        result = await self._session.execute(
            select(AggContentVersion)
            .where(AggContentVersion.raw_item_id == raw_item_id)
            .order_by(AggContentVersion.version_no.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()
        next_no = (last.version_no + 1) if last else 1

        if last is not None:
            last.is_current = False

        version = AggContentVersion(
            raw_item_id=raw_item_id,
            version_no=next_no,
            original_text=original_text,
            normalized_text=normalized_text,
            removed_boilerplate=removed_boilerplate,
            normalization_version=normalization_version,
            is_current=True,
        )
        self._session.add(version)
        await self._session.flush()
        return version

    async def get_current_content_version(
        self, raw_item_id: int
    ) -> AggContentVersion | None:
        result = await self._session.execute(
            select(AggContentVersion).where(
                AggContentVersion.raw_item_id == raw_item_id,
                AggContentVersion.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def link_post(self, raw_item_id: int, post_id: int) -> None:
        item = await self._session.get(AggRawItem, raw_item_id)
        if item:
            item.post_id = post_id
            await self._session.flush()

    async def link_listing(self, raw_item_id: int, listing_id: int) -> None:
        item = await self._session.get(AggRawItem, raw_item_id)
        if item:
            item.listing_id = listing_id
            await self._session.flush()

    async def link_spot(self, raw_item_id: int, spot_id: int) -> None:
        item = await self._session.get(AggRawItem, raw_item_id)
        if item:
            item.spot_id = spot_id
            await self._session.flush()


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def enqueue(self, raw_item_id: int, stage: ProcessingStage) -> AggProcessingTask:
        stmt = (
            pg_insert(AggProcessingTask)
            .values(raw_item_id=raw_item_id, stage=stage.value, status=TaskStatus.PENDING.value)
            .on_conflict_do_update(
                index_elements=["raw_item_id", "stage"],
                set_={"status": TaskStatus.PENDING.value, "available_at": datetime.now(timezone.utc)},
            )
            .returning(AggProcessingTask)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()

    async def claim_pending(
        self, stage: ProcessingStage, limit: int
    ) -> list[AggProcessingTask]:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(AggProcessingTask)
            .where(
                AggProcessingTask.stage == stage.value,
                AggProcessingTask.status == TaskStatus.PENDING.value,
                AggProcessingTask.available_at <= now,
            )
            .order_by(AggProcessingTask.available_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        tasks = list(result.scalars())
        for task in tasks:
            task.status = TaskStatus.IN_PROGRESS.value
        await self._session.flush()
        return tasks

    async def claim_failed(
        self, stage: ProcessingStage, limit: int
    ) -> list[AggProcessingTask]:
        result = await self._session.execute(
            select(AggProcessingTask)
            .where(
                AggProcessingTask.stage == stage.value,
                AggProcessingTask.status == TaskStatus.FAILED.value,
            )
            .order_by(AggProcessingTask.updated_at.asc())
            .limit(limit)
        )
        tasks = list(result.scalars())
        for task in tasks:
            task.status = TaskStatus.PENDING.value
            task.available_at = datetime.now(timezone.utc)
        await self._session.flush()
        return tasks

    async def mark_done(self, task: AggProcessingTask) -> None:
        task.status = TaskStatus.DONE.value
        await self._session.flush()

    async def mark_failed(self, task: AggProcessingTask, error: str) -> None:
        task.status = TaskStatus.FAILED.value
        task.attempts += 1
        task.last_error = error[:2000]
        backoff_seconds = min(3600, 30 * (2 ** min(task.attempts, 8)))
        task.available_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
        await self._session.flush()


class ClassificationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_cached(
        self, content_version_id: int, model: str, prompt_version: str
    ) -> AggClassification | None:
        result = await self._session.execute(
            select(AggClassification).where(
                AggClassification.content_version_id == content_version_id,
                AggClassification.model == model,
                AggClassification.prompt_version == prompt_version,
            )
        )
        return result.scalar_one_or_none()

    async def store(
        self,
        content_version_id: int,
        *,
        model: str,
        prompt_version: str,
        decision: str,
        result: dict,
        tokens_in: int | None,
        tokens_out: int | None,
        cost_estimate_usd: float | None,
    ) -> AggClassification:
        record = AggClassification(
            content_version_id=content_version_id,
            model=model,
            prompt_version=prompt_version,
            decision=decision,
            result=result,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimate_usd=cost_estimate_usd,
        )
        self._session.add(record)
        await self._session.flush()
        return record


class CursorRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, source_key: str, cursor_type: str) -> dict | None:
        result = await self._session.execute(
            select(AggCursor).where(
                AggCursor.source_key == source_key, AggCursor.cursor_type == cursor_type
            )
        )
        cursor = result.scalar_one_or_none()
        return cursor.position if cursor else None

    async def set(self, source_key: str, cursor_type: str, position: dict) -> None:
        stmt = (
            pg_insert(AggCursor)
            .values(source_key=source_key, cursor_type=cursor_type, position=position)
            .on_conflict_do_update(
                index_elements=["source_key", "cursor_type"],
                set_={"position": position},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()


class RunRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def start(self, source_key: str, command: str) -> AggRun:
        run = AggRun(source_key=source_key, command=command, status="running")
        self._session.add(run)
        await self._session.flush()
        return run

    async def finish(self, run: AggRun, status: str, stats: dict, error: str | None = None) -> None:
        run.status = status
        run.stats = stats
        run.error = error
        run.finished_at = datetime.now(timezone.utc)
        await self._session.flush()


class CandidateRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(
        self, raw_item_id: int, kind: str, raw_name: str, evidence: str | None
    ) -> AggUnresolvedCandidate:
        candidate = AggUnresolvedCandidate(
            raw_item_id=raw_item_id, kind=kind, raw_name=raw_name, evidence=evidence
        )
        self._session.add(candidate)
        await self._session.flush()
        return candidate


class MediaAttachmentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(
        self, raw_item_id: int, attachment_index: int, source_ref: str, media_type: str
    ) -> AggMediaAttachment:
        stmt = (
            pg_insert(AggMediaAttachment)
            .values(
                raw_item_id=raw_item_id,
                attachment_index=attachment_index,
                source_ref=source_ref,
                media_type=media_type,
            )
            .on_conflict_do_nothing(
                index_elements=["raw_item_id", "attachment_index"]
            )
            .returning(AggMediaAttachment)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        await self._session.flush()
        if row is not None:
            return row
        existing = await self._session.execute(
            select(AggMediaAttachment).where(
                AggMediaAttachment.raw_item_id == raw_item_id,
                AggMediaAttachment.attachment_index == attachment_index,
            )
        )
        return existing.scalar_one()

    async def pending_for_item(self, raw_item_id: int) -> list[AggMediaAttachment]:
        result = await self._session.execute(
            select(AggMediaAttachment).where(
                AggMediaAttachment.raw_item_id == raw_item_id,
                AggMediaAttachment.download_state != "uploaded",
            ).order_by(AggMediaAttachment.attachment_index)
        )
        return list(result.scalars())

    async def all_for_item(self, raw_item_id: int) -> list[AggMediaAttachment]:
        result = await self._session.execute(
            select(AggMediaAttachment)
            .where(AggMediaAttachment.raw_item_id == raw_item_id)
            .order_by(AggMediaAttachment.attachment_index)
        )
        return list(result.scalars())

    async def mark_uploaded(self, attachment: AggMediaAttachment, media_file_id: int) -> None:
        attachment.download_state = "uploaded"
        attachment.media_file_id = media_file_id
        await self._session.flush()

    async def mark_failed(self, attachment: AggMediaAttachment, error: str) -> None:
        attachment.download_state = "failed"
        attachment.attempts += 1
        attachment.last_error = error[:2000]
        await self._session.flush()
