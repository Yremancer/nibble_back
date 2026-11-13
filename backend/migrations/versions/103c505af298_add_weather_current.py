from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '103c505af298'
down_revision: Union[str, Sequence[str], None] = '86d51179ce59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('weather_current',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('city_id', sa.Integer(), nullable=True),
    sa.Column('spot_id', sa.BigInteger(), nullable=True),
    sa.Column('temp_c', sa.Numeric(precision=4, scale=1), nullable=False),
    sa.Column('condition', sa.String(length=20), nullable=False),
    sa.Column('wind_dir', sa.String(length=3), nullable=True),
    sa.Column('wind_speed_ms', sa.Numeric(precision=4, scale=1), nullable=True),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("condition IN ('clear', 'partly_cloudy', 'cloudy', 'rain', 'snow', 'fog')", name=op.f('ck_weather_current_condition')),
    sa.CheckConstraint('(city_id IS NULL) <> (spot_id IS NULL)', name=op.f('ck_weather_current_one_target')),
    sa.ForeignKeyConstraint(['city_id'], ['cities.id'], name=op.f('fk_weather_current_city_id_cities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['spot_id'], ['spots.id'], name=op.f('fk_weather_current_spot_id_spots'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_weather_current')),
    sa.UniqueConstraint('city_id', name=op.f('uq_weather_current_city_id')),
    sa.UniqueConstraint('spot_id', name=op.f('uq_weather_current_spot_id'))
    )


def downgrade() -> None:
    op.drop_table('weather_current')
