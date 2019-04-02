"""extra columns for planned races

Revision ID: cf0e97444677
Revises: 68b8ef45af85
Create Date: 2019-04-02 20:53:24.659681

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cf0e97444677'
down_revision = '68b8ef45af85'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('scheduled_race', sa.Column('entries_close_date', sa.Date(), nullable=True))
    op.add_column('scheduled_race', sa.Column('entry_status', sa.String(length=50), nullable=True))
    op.add_column('scheduled_race', sa.Column('is_removed', sa.Boolean(), nullable=True))
    op.add_column('scheduled_race', sa.Column('race_website_url', sa.String(length=250), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('scheduled_race', 'race_website_url')
    op.drop_column('scheduled_race', 'is_removed')
    op.drop_column('scheduled_race', 'entry_status')
    op.drop_column('scheduled_race', 'entries_close_date')
    # ### end Alembic commands ###
