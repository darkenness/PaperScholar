"""Add optional provider diagnostics and persisted generation parameters."""
from alembic import op
from app.core.maintenance_schema import ensure_maintenance_columns
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

def upgrade():
    ensure_maintenance_columns(op.get_bind())

def downgrade():
    for name in ("capability_status", "api_options", "display_name"):
        op.drop_column("api_key_configs", name)
    op.drop_column("generation_tasks", "request_params")
