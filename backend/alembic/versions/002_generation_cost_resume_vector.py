"""Add cost, resume, optimizer, and vector export fields.

Revision ID: 002
Revises: 001
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("generation_tasks", sa.Column("optimize_input", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("generation_tasks", sa.Column("vector_export", sa.String(length=10), nullable=True))
    op.add_column("generation_tasks", sa.Column("cost_budget_usd", sa.Float(), nullable=True))
    op.add_column("generation_tasks", sa.Column("cost_estimated_usd", sa.Float(), nullable=True))
    op.add_column("generation_tasks", sa.Column("cost_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("generation_tasks", sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("generation_tasks", sa.Column("user_feedback", sa.Text(), nullable=True))
    op.add_column("generation_results", sa.Column("pdf_path", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("generation_results", "pdf_path")
    op.drop_column("generation_tasks", "user_feedback")
    op.drop_column("generation_tasks", "parent_task_id")
    op.drop_column("generation_tasks", "cost_details")
    op.drop_column("generation_tasks", "cost_estimated_usd")
    op.drop_column("generation_tasks", "cost_budget_usd")
    op.drop_column("generation_tasks", "vector_export")
    op.drop_column("generation_tasks", "optimize_input")
