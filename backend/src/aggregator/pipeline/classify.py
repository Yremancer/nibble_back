"""Этап классификации: берёт текущую версию содержимого, проверяет кеш
(agg_classifications по content_version_id+model+prompt_version), иначе
зовёт DeepSeek. Сбой/таймаут/невалидный JSON не удаляют публикацию —
задача остаётся для повтора (retry-failed --stage classify)."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import ProcessingStage
from src.aggregator.repository import ClassificationRepository, RawItemRepository, TaskRepository
from src.llm.client import DeepSeekClient
from src.llm.exceptions import LlmError
from src.llm.prompts import load_prompt
from src.llm.schemas import ClassificationResult
from src.llm.settings import LlmSettings

logger = logging.getLogger(__name__)


class ClassifyStage:
    def __init__(
        self,
        session: AsyncSession,
        llm_client: DeepSeekClient,
        llm_settings: LlmSettings,
    ):
        self._session = session
        self._llm = llm_client
        self._settings = llm_settings
        self._raw_items = RawItemRepository(session)
        self._classifications = ClassificationRepository(session)
        self._tasks = TaskRepository(session)

    async def run_for_raw_item(self, raw_item_id: int) -> ClassificationResult | None:
        content_version = await self._raw_items.get_current_content_version(raw_item_id)
        if content_version is None:
            raise ValueError(f"нет текущей версии содержимого для {raw_item_id}")

        cached = await self._classifications.get_cached(
            content_version.id, self._settings.DEEPSEEK_MODEL, self._settings.PROMPT_VERSION
        )
        if cached is not None:
            return ClassificationResult.model_validate(cached.result)

        if not self._llm.is_configured:
            logger.info("DeepSeek не настроен, пост %s отправлен в очередь", raw_item_id)
            return None

        prompt = load_prompt(f"classify_{self._settings.PROMPT_VERSION}")
        text = content_version.normalized_text or ""

        result, meta = await self._llm.classify_post(prompt, text)

        await self._classifications.store(
            content_version.id,
            model=self._settings.DEEPSEEK_MODEL,
            prompt_version=self._settings.PROMPT_VERSION,
            decision=result.decision.value,
            result=result.model_dump(mode="json"),
            tokens_in=meta.get("tokens_in"),
            tokens_out=meta.get("tokens_out"),
            cost_estimate_usd=None,
        )
        return result


async def process_classify_tasks(
    session: AsyncSession,
    llm_client: DeepSeekClient,
    llm_settings: LlmSettings,
    limit: int,
) -> dict:
    tasks_repo = TaskRepository(session)
    stage = ClassifyStage(session, llm_client, llm_settings)

    tasks = await tasks_repo.claim_pending(ProcessingStage.CLASSIFY, limit)
    done = failed = skipped = 0

    for task in tasks:
        try:
            result = await stage.run_for_raw_item(task.raw_item_id)
            if result is None:
                await tasks_repo.mark_failed(task, "DeepSeek не настроен")
                skipped += 1
                continue
            await tasks_repo.mark_done(task)
            if result.decision.value != "discard":
                await tasks_repo.enqueue(task.raw_item_id, ProcessingStage.RESOLVE)
            done += 1
        except LlmError as exc:
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1
        except Exception as exc:  # noqa: BLE001 - не терять задачу при любой ошибке
            logger.exception("classify stage failed for raw_item %s", task.raw_item_id)
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1

    return {"done": done, "failed": failed, "skipped": skipped}
