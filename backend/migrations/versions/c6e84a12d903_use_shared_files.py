
import sqlalchemy as sa
from alembic import op

revision = "c6e84a12d903"
down_revision = ("b79d6e2410ac", "bd43c17d2707")
branch_labels = None
depends_on = None

RELATIONS = (
    ("post_media", "RESTRICT"),
    ("listing_media", "RESTRICT"),
    ("agg_media_attachments", "SET NULL"),
)


def upgrade() -> None:
    from src.settings import settings

    bind = op.get_bind()
    op.execute(
        "LOCK TABLE media_files, files, post_media, listing_media, "
        "agg_media_attachments IN ACCESS EXCLUSIVE MODE"
    )
    invalid = bind.execute(sa.text(
        "SELECT count(*) FROM media_files WHERE bucket != :bucket "
        "OR size_bytes < 0 OR size_bytes > 2147483647"
    ), {"bucket": settings.S3_BUCKET}).scalar_one()
    if invalid:
        raise RuntimeError(
            "media_files: incompatible bucket or file size; "
            "move objects to S3_BUCKET and check sizes before upgrading"
        )
    if bind.execute(sa.text(
        "SELECT EXISTS (SELECT object_key FROM media_files "
        "GROUP BY object_key HAVING count(*) > 1)"
    )).scalar_one():
        raise RuntimeError("media_files: duplicate object_key; resolve before upgrading")
    if bind.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM media_files m JOIN files f "
        "ON f.key = m.object_key WHERE f.size != m.size_bytes "
        "OR f.content_type != m.mime_type)"
    )).scalar_one():
        raise RuntimeError("media_files: conflicting files metadata for the same S3 key")

    op.execute("""
        CREATE TEMP TABLE shared_file_map ON COMMIT DROP AS
        SELECT m.id AS old_id,
               COALESCE(f.id::bigint, (SELECT COALESCE(max(id), 0) FROM files)
                        + row_number() OVER (ORDER BY m.id)) AS new_id
        FROM media_files m LEFT JOIN files f ON f.key = m.object_key
    """)
    op.execute("""
        INSERT INTO files (id, key, original_name, content_type, size, created_at)
        SELECT map.new_id, m.object_key,
               regexp_replace(m.object_key, '^.*/', ''), m.mime_type,
               m.size_bytes, m.created_at AT TIME ZONE 'UTC'
        FROM media_files m JOIN shared_file_map map ON map.old_id = m.id
        WHERE NOT EXISTS (SELECT 1 FROM files f WHERE f.key = m.object_key)
    """)
    for table, ondelete in RELATIONS:
        op.drop_constraint(
            f"fk_{table}_media_file_id_media_files", table, type_="foreignkey"
        )
        owner = {"post_media": "post_id", "listing_media": "listing_id"}.get(table)
        if owner:
            op.drop_constraint(f"uq_{table}_{owner}_media_file_id", table, type_="unique")
        op.execute(sa.text(
            f"UPDATE {table} t SET media_file_id = map.new_id "
            "FROM shared_file_map map WHERE t.media_file_id = map.old_id"
        ))
        op.alter_column(
            table, "media_file_id", existing_type=sa.BigInteger(), type_=sa.Integer()
        )
        op.create_foreign_key(
            f"fk_{table}_media_file_id_files",
            table,
            "files",
            ["media_file_id"],
            ["id"],
            ondelete=ondelete,
        )
        if owner:
            op.create_unique_constraint(f"uq_{table}_{owner}_media_file_id", table, [owner, "media_file_id"])
    op.drop_index("ix_media_files_sha256", table_name="media_files")
    op.drop_table("media_files")
    op.execute("""
        SELECT setval(pg_get_serial_sequence('files', 'id'),
                      COALESCE(max(id), 1), max(id) IS NOT NULL) FROM files
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if any(bind.execute(sa.text(
        f"SELECT EXISTS (SELECT 1 FROM {table} WHERE media_file_id IS NOT NULL)"
    )).scalar_one() for table, _ in RELATIONS):
        raise RuntimeError(
            "Cannot downgrade shared files with attachments; restore the pre-upgrade backup"
        )
    op.create_table(
        "media_files",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("bucket", sa.String(100), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration_s", sa.Integer()),
        sa.Column("preview_object_key", sa.Text()),
        sa.Column(
            "upload_state", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "upload_state IN ('pending', 'uploaded', 'failed')",
            name=op.f("ck_media_files_upload_state"),
        ),
    )
    op.create_index("ix_media_files_sha256", "media_files", ["sha256"], unique=True)
    for table, ondelete in RELATIONS:
        op.drop_constraint(f"fk_{table}_media_file_id_files", table, type_="foreignkey")
        op.alter_column(
            table, "media_file_id", existing_type=sa.Integer(), type_=sa.BigInteger()
        )
        op.create_foreign_key(
            f"fk_{table}_media_file_id_media_files",
            table,
            "media_files",
            ["media_file_id"],
            ["id"],
            ondelete=ondelete,
        )
