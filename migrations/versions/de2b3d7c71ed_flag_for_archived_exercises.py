"""flag for archived exercises

Revision ID: de2b3d7c71ed
Revises: d2ec7594002f
Create Date: 2019-02-03 10:34:21.993294

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'de2b3d7c71ed'
down_revision = 'd2ec7594002f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('exercise_type', sa.Column('is_archived', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('exercise_type', 'is_archived')
    # ### end Alembic commands ###
