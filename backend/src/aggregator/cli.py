
import argparse
import asyncio
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aggregator.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aggregator")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth-telegram", help="первичная авторизация Telegram-сессии")

    doctor = sub.add_parser("doctor", help="проверка конфигурации и подключений")
    doctor.add_argument("--dry-run", action="store_true", default=True)

    sync = sub.add_parser("sync", help="синхронизация источника")
    sync.add_argument("--source", choices=["all", "telegram", "farpost"], default="all")
    sync.add_argument("--limit", type=int, default=None, help="лимит публикаций/карточек для пробного запуска")
    sync.add_argument("--pages", type=int, default=None, help="лимит страниц (farpost)")
    sync.add_argument("--dry-run", action="store_true", help="не писать доменные сущности")
    sync.add_argument("--channel", help="один активный Telegram-канал из sources.json")

    backfill = sub.add_parser("backfill", help="загрузка истории")
    backfill.add_argument("--source", choices=["telegram", "farpost", "fishing_vl"], required=True)
    backfill.add_argument("--since", type=str, default=None, help="YYYY-MM-DD")
    backfill.add_argument("--limit", type=int, default=None)
    backfill.add_argument("--pages", type=int, default=None)
    backfill.add_argument("--channel", help="один активный Telegram-канал из sources.json")

    reprocess = sub.add_parser("reprocess", help="повторная обработка этапа")
    reprocess.add_argument(
        "--stage",
        choices=["normalize", "classify", "resolve", "dedup", "media", "publish"],
        required=True,
    )
    reprocess.add_argument("--limit", type=int, default=100)
    sub.add_parser("worker", help="непрерывная обработка очереди и отложенных повторов")
    sub.add_parser("schedule", help="синхронизация Telegram по расписанию и обработка повторов")
    manual = sub.add_parser("import-listings", help="импорт вручную собранных объявлений Farpost")
    manual.add_argument("--input", required=True, help="путь к CSV или JSON внутри контейнера")
    manual.add_argument("--city", help="город для строк без явного города")

    retry = sub.add_parser("retry-failed", help="повторить ошибочные задачи этапа")
    retry.add_argument(
        "--stage",
        choices=["normalize", "classify", "resolve", "dedup", "media", "publish"],
        required=True,
    )
    retry.add_argument("--limit", type=int, default=100)

    export = sub.add_parser("export", help="JSONL-экспорт для диагностики")
    export.add_argument("--kind", choices=["posts", "listings"], required=True)
    export.add_argument("--format", choices=["jsonl"], default="jsonl")
    export.add_argument("--output", type=str, default=None)

    sub.add_parser("status", help="состояние курсоров, очередей, последних запусков")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(dispatch(args)))


async def dispatch(args: argparse.Namespace) -> int | None:
    from src.aggregator import commands

    if args.command == "auth-telegram":
        await commands.cmd_auth_telegram()
    elif args.command == "doctor":
        return await commands.cmd_doctor()
    elif args.command == "worker":
        await commands.cmd_worker()
    elif args.command == "schedule":
        await commands.cmd_schedule()
    elif args.command == "import-listings":
        async with commands.command_run("farpost", args.command) as run_stats:
            run_stats.update(await commands.cmd_import_listings(args.input, args.city))
    elif args.command in ("sync", "backfill", "reprocess", "retry-failed"):
        source_key = getattr(args, "source", "pipeline")
        async with commands.command_run(source_key, args.command) as run_stats:
            if args.command == "sync":
                stats = await commands.cmd_sync(
                    source=args.source, limit=args.limit, pages=args.pages, dry_run=args.dry_run, channel=args.channel
                )
            elif args.command == "backfill":
                since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.since else None
                stats = await commands.cmd_backfill(
                    source=args.source, since=since, limit=args.limit, pages=args.pages, channel=args.channel
                )
            elif args.command == "reprocess":
                stats = await commands.cmd_reprocess(stage=args.stage, limit=args.limit)
            elif args.command == "retry-failed":
                stats = await commands.cmd_retry_failed(stage=args.stage, limit=args.limit)
            run_stats.update(stats)
    elif args.command == "export":
        await commands.cmd_export(kind=args.kind, output=args.output)
    elif args.command == "status":
        await commands.cmd_status()


if __name__ == "__main__":
    main()
