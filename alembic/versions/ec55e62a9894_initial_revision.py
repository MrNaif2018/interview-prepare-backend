"""Initial revision

Revision ID: ec55e62a9894
Revises:
Create Date: 2024-10-18 01:33:20.693215

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "ec55e62a9894"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "settings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("settings_pkey")),
    )
    op.create_index(op.f("settings_id_idx"), "settings", ["id"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("hashed_password", sa.Text(), nullable=True),
        sa.Column("permissions", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("users_pkey")),
    )
    op.create_index(op.f("users_email_idx"), "users", ["email"], unique=True)
    op.create_index(op.f("users_id_idx"), "users", ["id"], unique=False)
    op.create_table(
        "tokens",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("tokens_user_id_users_fkey"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("tokens_pkey")),
    )
    op.create_index(op.f("tokens_id_idx"), "tokens", ["id"], unique=False)
    op.create_index(op.f("tokens_user_id_idx"), "tokens", ["user_id"], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("tokens_user_id_idx"), table_name="tokens")
    op.drop_index(op.f("tokens_id_idx"), table_name="tokens")
    op.drop_table("tokens")
    op.drop_index(op.f("users_id_idx"), table_name="users")
    op.drop_index(op.f("users_email_idx"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("settings_id_idx"), table_name="settings")
    op.drop_table("settings")
    # ### end Alembic commands ###
