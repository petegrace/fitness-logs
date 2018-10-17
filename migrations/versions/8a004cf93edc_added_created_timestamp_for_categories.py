"""Added created timestamp for categories

Revision ID: 8a004cf93edc
Revises: 78e2298b7160
Create Date: 2018-10-17 21:32:13.644890

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a004cf93edc'
down_revision = '78e2298b7160'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('exercise_category', sa.Column('created_datetime', sa.DateTime(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('exercise_category', 'created_datetime')
    # ### end Alembic commands ###
