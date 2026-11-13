"""Add file metadata.

Revision ID: f2a9c7d1b408
Revises: 86d51179ce59
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a9c7d1b408"
down_revision = "86d51179ce59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("original_name", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
    )
    op.create_index(op.f("ix_files_key"), "files", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_files_key"), table_name="files")
    op.drop_table("files")
