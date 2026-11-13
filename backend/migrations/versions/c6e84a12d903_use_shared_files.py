"""Merge parsing and storage; use files for all media links."""

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
    for table, ondelete in RELATIONS:
        op.drop_constraint(
            f"fk_{table}_media_file_id_media_files", table, type_="foreignkey"
        )
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
    op.drop_index("ix_media_files_sha256", table_name="media_files")
    op.drop_table("media_files")


def downgrade() -> None:
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
