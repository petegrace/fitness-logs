"""Support for stretches as well as strength

Revision ID: 5139be8583c0
Revises: f4667ab21f4a
Create Date: 2018-10-14 13:46:37.675100

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5139be8583c0'
down_revision = 'f4667ab21f4a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('exercise_type', sa.Column('category', sa.String(length=50), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('exercise_type', 'category')
    # ### end Alembic commands ###