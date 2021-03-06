"""first bunch of tables

Revision ID: 4c94be31a48a
Revises: 
Create Date: 2018-10-02 19:50:26.999094

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4c94be31a48a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('password_hash', sa.String(length=128), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)
    op.create_table('exercise_type',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=True),
    sa.Column('measured_by', sa.String(length=50), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exercise_type_name'), 'exercise_type', ['name'], unique=False)
    op.create_table('exercise',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('exercise_type_id', sa.Integer(), nullable=True),
    sa.Column('exercise_datetime', sa.DateTime(), nullable=True),
    sa.Column('reps', sa.Integer(), nullable=True),
    sa.Column('created_datetime', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['exercise_type_id'], ['exercise_type.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exercise_exercise_datetime'), 'exercise', ['exercise_datetime'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_exercise_exercise_datetime'), table_name='exercise')
    op.drop_table('exercise')
    op.drop_index(op.f('ix_exercise_type_name'), table_name='exercise_type')
    op.drop_table('exercise_type')
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
    # ### end Alembic commands ###
