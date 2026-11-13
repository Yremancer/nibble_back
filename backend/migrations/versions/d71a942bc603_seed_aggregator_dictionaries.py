
import sqlalchemy as sa
from alembic import op

revision = "d71a942bc603"
down_revision = "c6e84a12d903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO cities (name, lat, lon, timezone)
        VALUES ('Владивосток', 43.115536, 131.885485, 'Asia/Vladivostok')
        ON CONFLICT (name) DO NOTHING
    """)
    connection = op.get_bind()
    for name, aliases in (
        ("Терпуг", ["терпуги"]),
        ("Корюшка", ["корюшки"]),
        ("Навага", ["наваги"]),
        ("Камбала", ["камбалы"]),
        ("Пиленгас", ["пеленгас"]),
        ("Краснопёрка", ["красноперка"]),
    ):
        connection.execute(sa.text("""
            INSERT INTO species (name, short_description, image_url, aliases)
            VALUES (:name, :name, '', :aliases)
            ON CONFLICT (name) DO NOTHING
        """), {"name": name, "aliases": aliases})
    for name in ("Спиннинг", "Поплавочная удочка", "Донная снасть", "Фидер", "Подлёдная ловля", "Троллинг"):
        connection.execute(sa.text("""
            INSERT INTO fishing_methods (name) VALUES (:name)
            ON CONFLICT (name) DO NOTHING
        """), {"name": name})
    op.execute("""
        INSERT INTO spots (city_id, name, lat, lon, aliases)
        SELECT c.id, 'Бухта Аякс', 43.029808, 131.940298, ARRAY['аякс', 'buhta-ajax']
        FROM cities c WHERE c.name = 'Владивосток'
          AND NOT EXISTS (SELECT 1 FROM spots s WHERE s.city_id = c.id AND s.name = 'Бухта Аякс')
    """)


def downgrade() -> None:
    pass
