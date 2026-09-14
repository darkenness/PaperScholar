"""Idempotent, additive upgrades for existing create_all installations."""
from sqlalchemy import inspect, text
COLUMNS = {"api_key_configs":{"display_name":"VARCHAR(100)", "api_options":"JSONB", "capability_status":"JSONB"}, "generation_tasks":{"request_params":"JSONB"}}

def ensure_maintenance_columns(connection):
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(727160914)"))
    existing_tables=set(inspect(connection).get_table_names())
    for table,columns in COLUMNS.items():
        if table not in existing_tables:
            continue
        existing={c["name"] for c in inspect(connection).get_columns(table)}
        for name,sql_type in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
