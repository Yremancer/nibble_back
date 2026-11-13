import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg import sql

from src.settings import settings


def prepare_legacy(db):
    command.upgrade(Config("alembic.ini"), "b79d6e2410ac")
    command.upgrade(Config("alembic.ini"), "bd43c17d2707")
    db.execute("""
        INSERT INTO files (id, key, original_name, content_type, size)
        VALUES (1, 'unrelated.jpg', 'unrelated.jpg', 'image/jpeg', 10),
               (2, 'existing.jpg', 'existing.jpg', 'image/jpeg', 20);
        INSERT INTO sources (id, type, name) VALUES (1, 'telegram', 'test');
        INSERT INTO posts (id, source_id, text) VALUES (1, 1, 'test');
        INSERT INTO listings (id, farpost_id, title, url) VALUES (1, '1', 'test', 'test');
        INSERT INTO agg_raw_items
            (id, kind, source_key, external_id, raw_payload, content_hash, parser_version)
        VALUES (1, 'telegram_post', 'test', '1', '{}', 'test', 'v1');
    """)
    for file_id, key, size in ((1, "legacy.jpg", 30), (2, "existing.jpg", 20), (3000000000, "large-id.jpg", 40)):
        db.execute(
            "INSERT INTO media_files (id, bucket, object_key, sha256, mime_type, size_bytes) "
            "VALUES (%s, %s, %s, %s, 'image/jpeg', %s)",
            (file_id, settings.S3_BUCKET, key, str(file_id).zfill(64), size),
        )
    db.execute("""
        INSERT INTO post_media (post_id, media_file_id, type) VALUES (1, 1, 'photo'), (1, 2, 'photo');
        INSERT INTO listing_media (listing_id, media_file_id, type) VALUES (1, 3000000000, 'photo');
        INSERT INTO agg_media_attachments
            (raw_item_id, attachment_index, source_ref, media_type, media_file_id)
        VALUES (1, 0, 'test:1', 'photo', 1), (1, 1, 'test:2', 'photo', NULL);
    """)


def test_fresh_install(migration_db):
    command.upgrade(Config("alembic.ini"), "head")
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert migration_db.execute("SELECT version_num FROM alembic_version").fetchone() == (head,)
    assert migration_db.execute("SELECT count(*) FROM files").fetchone() == (0,)
    assert migration_db.execute("SELECT count(*) FROM species").fetchone() == (6,)
    assert migration_db.execute("SELECT count(*) FROM fishing_methods").fetchone() == (6,)
    assert migration_db.execute("SELECT name FROM spots").fetchall() == [("Бухта Аякс",)]


def test_upgrade_preserves_all_relations_and_sequence(migration_db):
    prepare_legacy(migration_db)
    command.upgrade(Config("alembic.ini"), "head")
    for table, expected in (
        ("post_media", ["existing.jpg", "legacy.jpg"]),
        ("listing_media", ["large-id.jpg"]),
        ("agg_media_attachments", ["legacy.jpg"]),
    ):
        rows = migration_db.execute(sql.SQL(
            "SELECT f.key FROM {} t JOIN files f ON f.id = t.media_file_id ORDER BY f.key"
        ).format(sql.Identifier(table))).fetchall()
        assert [row[0] for row in rows] == expected
    assert migration_db.execute("SELECT key FROM files WHERE id = 1").fetchone() == ("unrelated.jpg",)
    assert migration_db.execute("SELECT count(*) FROM files WHERE key = 'existing.jpg'").fetchone() == (1,)
    assert migration_db.execute("SELECT count(*) FROM agg_media_attachments WHERE media_file_id IS NULL").fetchone() == (1,)
    highest = migration_db.execute("SELECT max(id) FROM files").fetchone()[0]
    inserted = migration_db.execute(
        "INSERT INTO files (key, original_name, content_type, size) "
        "VALUES ('next.jpg', 'next.jpg', 'image/jpeg', 1) RETURNING id"
    ).fetchone()[0]
    assert inserted > highest
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(Config("alembic.ini"), "b79d6e2410ac")


def test_upgrade_can_swap_existing_ids(migration_db):
    prepare_legacy(migration_db)
    migration_db.execute("""
        UPDATE files SET key = 'legacy.jpg', size = 30 WHERE id = 1;
        UPDATE media_files SET object_key = 'existing.jpg', size_bytes = 20 WHERE id = 1;
        UPDATE media_files SET object_key = 'legacy.jpg', size_bytes = 30 WHERE id = 2;
    """)
    command.upgrade(Config("alembic.ini"), "head")
    assert migration_db.execute(
        "SELECT media_file_id FROM post_media ORDER BY id"
    ).fetchall() == [(2,), (1,)]


@pytest.mark.parametrize("invalid_sql, message", [
    ("UPDATE media_files SET bucket = 'another-bucket' WHERE id = 1", "incompatible bucket"),
    ("UPDATE media_files SET size_bytes = 2147483648 WHERE id = 1", "file size"),
    ("UPDATE media_files SET size_bytes = 99 WHERE id = 2", "conflicting files metadata"),
    ("UPDATE media_files SET object_key = 'legacy.jpg' WHERE id = 2", "duplicate object_key"),
])
def test_unsafe_upgrade_rolls_back(migration_db, invalid_sql, message):
    prepare_legacy(migration_db)
    migration_db.execute(invalid_sql)
    with pytest.raises(RuntimeError, match=message):
        command.upgrade(Config("alembic.ini"), "head")
    assert migration_db.execute("SELECT count(*) FROM media_files").fetchone() == (3,)
    assert migration_db.execute("SELECT media_file_id FROM post_media ORDER BY id").fetchall() == [(1,), (2,)]
    assert migration_db.execute("SELECT count(*) FROM files").fetchone() == (2,)
