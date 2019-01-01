"""extra activity attributes

Revision ID: 09e821a4ff89
Revises: 120f2c195c85
Create Date: 2019-01-01 22:26:15.662377

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '09e821a4ff89'
down_revision = '120f2c195c85'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('activity', sa.Column('description', sa.String(length=1000), nullable=True))
    op.add_column('activity', sa.Column('is_bad_elevation_data', sa.Boolean(), nullable=True))
    op.add_column('activity', sa.Column('is_fully_parsed', sa.Boolean(), nullable=True))
    op.add_column('activity', sa.Column('total_elevation_gain', sa.Numeric(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('activity', 'total_elevation_gain')
    op.drop_column('activity', 'is_fully_parsed')
    op.drop_column('activity', 'is_bad_elevation_data')
    op.drop_column('activity', 'description')
    # ### end Alembic commands ###
