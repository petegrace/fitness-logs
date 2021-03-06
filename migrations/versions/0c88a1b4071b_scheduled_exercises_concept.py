"""Scheduled Exercises concept

Revision ID: 0c88a1b4071b
Revises: dc7250f14b2b
Create Date: 2018-10-13 16:08:40.993428

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0c88a1b4071b'
down_revision = 'dc7250f14b2b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('scheduled_exercise',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('exercise_type_id', sa.Integer(), nullable=True),
    sa.Column('scheduled_day', sa.String(length=10), nullable=True),
    sa.Column('sets', sa.Integer(), nullable=True),
    sa.Column('reps', sa.Integer(), nullable=True),
    sa.Column('seconds', sa.Integer(), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['exercise_type_id'], ['exercise_type.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('scheduled_exercise')
    # ### end Alembic commands ###
