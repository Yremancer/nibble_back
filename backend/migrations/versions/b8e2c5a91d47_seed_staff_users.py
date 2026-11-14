"""seed staff users: admin, moderator, regular user

Пароли берутся из окружения (SEED_ADMIN_PASSWORD, SEED_MODERATOR_PASSWORD,
SEED_USER_PASSWORD), в репозитории их нет. Пользователь создаётся, только если
его пароль задан; email можно переопределить (SEED_<РОЛЬ>_EMAIL). Если такой
email уже есть, роль и пароль обновляются.
"""

import os

import sqlalchemy as sa
from alembic import op
from pwdlib import PasswordHash

revision = "b8e2c5a91d47"
down_revision = "6836e6d11d13"
branch_labels = None
depends_on = None

MIN_PASSWORD_LENGTH = 8

# (роль, префикс переменных окружения, email по умолчанию, имя)
SEEDS = (
    ("admin", "SEED_ADMIN", "admin@example.com", "Admin"),
    ("moderator", "SEED_MODERATOR", "moderator@example.com", "Moderator"),
    ("user", "SEED_USER", "user@example.com", "User"),
)


def upgrade() -> None:
    bind = op.get_bind()
    hasher = PasswordHash.recommended()
    city_id = bind.execute(sa.text("SELECT id FROM cities ORDER BY id LIMIT 1")).scalar()
    for role, prefix, default_email, name in SEEDS:
        password = os.environ.get(f"{prefix}_PASSWORD")
        if not password:
            continue
        if len(password) < MIN_PASSWORD_LENGTH:
            raise RuntimeError(
                f"{prefix}_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        if city_id is None:
            raise RuntimeError("Cannot seed users: there are no cities in the database")
        email = os.environ.get(f"{prefix}_EMAIL", default_email).strip().lower()
        bind.execute(
            sa.text(
                """
                INSERT INTO users (display_name, email, password_hash, city_id, role)
                VALUES (:name, :email, :password_hash, :city_id, :role)
                ON CONFLICT (email) DO UPDATE
                SET role = EXCLUDED.role, password_hash = EXCLUDED.password_hash
                """
            ),
            {
                "name": name,
                "email": email,
                "password_hash": hasher.hash(password),
                "city_id": city_id,
                "role": role,
            },
        )


def downgrade() -> None:
    # Учётные записи не удаляем: к ним уже могли привязаться посты и подписки.
    pass
