"""extra column to specify source of training plan generated activity

Revision ID: 2f5c358356f4
Revises: a4deab1aba3f
Create Date: 2019-04-28 09:11:58.670327

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f5c358356f4'
down_revision = 'a4deab1aba3f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('scheduled_activity', sa.Column('source', sa.String(length=50), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('scheduled_activity', 'source')
    # ### end Alembic commands ###
