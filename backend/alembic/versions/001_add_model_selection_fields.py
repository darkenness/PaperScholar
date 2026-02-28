"""Add chat_key_id and image_key_id to generation_tasks for model selection.

Revision ID: 001
Revises: None
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generation_tasks", sa.Column("chat_key_id", sa.Integer(), nullable=True))
    op.add_column("generation_tasks", sa.Column("image_key_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("generation_tasks", "image_key_id")
    op.drop_column("generation_tasks", "chat_key_id")
