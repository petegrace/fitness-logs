"""classes to support templates

Revision ID: 2ca69820bd3f
Revises: 8e4f2325e35d
Create Date: 2019-01-27 13:57:19.844672

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2ca69820bd3f'
down_revision = '8e4f2325e35d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('training_plan_template',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=True),
    sa.Column('description', sa.String(length=1000), nullable=True),
    sa.Column('link_url', sa.String(length=250), nullable=True),
    sa.Column('link_text', sa.String(length=100), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('template_exercise_category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('template_id', sa.Integer(), nullable=True),
    sa.Column('category_name', sa.String(length=25), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['template_id'], ['training_plan_template.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('template_exercise_type',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=True),
    sa.Column('measured_by', sa.String(length=50), nullable=True),
    sa.Column('template_exercise_category_id', sa.Integer(), nullable=True),
    sa.Column('default_reps', sa.Integer(), nullable=True),
    sa.Column('default_seconds', sa.Integer(), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['template_exercise_category_id'], ['template_exercise_category.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_template_exercise_type_name'), 'template_exercise_type', ['name'], unique=False)
    op.create_table('template_scheduled_exercise',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('template_exercise_type_id', sa.Integer(), nullable=True),
    sa.Column('scheduled_day', sa.String(length=10), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['template_exercise_type_id'], ['template_exercise_type.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('template_scheduled_exercise')
    op.drop_index(op.f('ix_template_exercise_type_name'), table_name='template_exercise_type')
    op.drop_table('template_exercise_type')
    op.drop_table('template_exercise_category')
    op.drop_table('training_plan_template')
    # ### end Alembic commands ###