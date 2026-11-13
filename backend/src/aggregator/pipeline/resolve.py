
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from src.aggregator.models import CandidateKind, ProcessingStage
from src.aggregator.repository import CandidateRepository, RawItemRepository, TaskRepository
from src.aggregator.resolve.dictionary import DictionaryResolver
from src.llm.schemas import ClassificationResult

logger = logging.getLogger(__name__)


class ResolvedFields:
    __slots__ = ("spot_id", "method_id", "species", "unresolved_species", "unresolved_spots")

    def __init__(self):
        self.spot_id: int | None = None
        self.method_id: int | None = None
        self.species: list[dict] = []
        self.unresolved_species: list[tuple[str, str]] = []
        self.unresolved_spots: list[tuple[str, str]] = []


async def resolve_classification(
    resolver: DictionaryResolver, result: ClassificationResult
) -> ResolvedFields:
    resolved = ResolvedFields()

    spot_candidates: set[int] = set()
    for mention in result.location_mentions:
        spot_id = await resolver.resolve_spot(mention.text)
        if spot_id is not None:
            spot_candidates.add(spot_id)
        else:
            resolved.unresolved_spots.append((mention.text, mention.evidence))

    if len(spot_candidates) == 1:
        resolved.spot_id = next(iter(spot_candidates))

    method_candidates: set[int] = set()
    for mention in result.methods:
        method_id = await resolver.resolve_method(mention.name)
        if method_id is not None:
            method_candidates.add(method_id)
    if len(method_candidates) == 1:
        resolved.method_id = next(iter(method_candidates))

    for species_mention in result.species:
        species_id = await resolver.resolve_species(species_mention.name)
        if species_id is not None:
            resolved.species.append(
                {
                    "species_id": species_id,
                    "quantity": species_mention.quantity,
                    "max_weight_g": species_mention.max_weight_g,
                }
            )
        else:
            resolved.unresolved_species.append(
                (species_mention.name, species_mention.evidence)
            )

    return resolved


async def process_resolve_tasks(session: AsyncSession, limit: int) -> dict:
    from src.aggregator.repository import ClassificationRepository

    tasks_repo = TaskRepository(session)
    raw_items_repo = RawItemRepository(session)
    classifications_repo = ClassificationRepository(session)
    candidates_repo = CandidateRepository(session)
    resolver = DictionaryResolver(session)

    tasks = await tasks_repo.claim_pending(ProcessingStage.RESOLVE, limit)
    done = failed = 0

    for task in tasks:
        try:
            content_version = await raw_items_repo.get_current_content_version(
                task.raw_item_id
            )
            if content_version is None:
                await tasks_repo.mark_failed(task, "нет текущей версии содержимого")
                failed += 1
                continue

            from src.llm.settings import llm_settings

            cached = await classifications_repo.get_cached(
                content_version.id, llm_settings.DEEPSEEK_MODEL, llm_settings.PROMPT_VERSION
            )
            if cached is None:
                await tasks_repo.mark_failed(task, "классификация ещё не выполнена")
                failed += 1
                continue

            result = ClassificationResult.model_validate(cached.result)
            resolved = await resolve_classification(resolver, result)

            for name, evidence in resolved.unresolved_species:
                await candidates_repo.add(
                    task.raw_item_id, CandidateKind.SPECIES.value, name, evidence
                )
            for name, evidence in resolved.unresolved_spots:
                await candidates_repo.add(
                    task.raw_item_id, CandidateKind.SPOT.value, name, evidence
                )

            await tasks_repo.mark_done(task)
            await tasks_repo.enqueue(task.raw_item_id, ProcessingStage.DEDUP)
            done += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("resolve stage failed for raw_item %s", task.raw_item_id)
            await tasks_repo.mark_failed(task, str(exc))
            failed += 1

    return {"done": done, "failed": failed}
