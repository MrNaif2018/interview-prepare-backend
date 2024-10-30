"""Add comments

Revision ID: 9780fcfe21b4
Revises: ac225f71ffe0
Create Date: 2024-10-30 01:48:35.875947

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "9780fcfe21b4"
down_revision = "ac225f71ffe0"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("questions", sa.Column("comments", sa.JSON(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("questions", "comments")
    # ### end Alembic commands ###