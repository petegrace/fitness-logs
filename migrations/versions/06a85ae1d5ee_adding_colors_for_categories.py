"""Adding colors for categories

Revision ID: 06a85ae1d5ee
Revises: 4d25fcbb02aa
Create Date: 2018-11-18 17:03:34.973364

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '06a85ae1d5ee'
down_revision = '4d25fcbb02aa'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('exercise_category', sa.Column('fill_color', sa.String(length=25), nullable=True))
    op.add_column('exercise_category', sa.Column('line_color', sa.String(length=25), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('exercise_category', 'line_color')
    op.drop_column('exercise_category', 'fill_color')
    # ### end Alembic commands ###
