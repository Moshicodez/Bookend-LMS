from sqlalchemy import inspect

from .extensions import db


SQLITE_COLUMN_UPGRADES = {
    "books": {
        "kind": "VARCHAR(30) NOT NULL DEFAULT 'standard'",
        "cover": "VARCHAR(255)",
    },
    "loans": {
        "fee_paid": "BOOLEAN NOT NULL DEFAULT 0",
        "lost": "BOOLEAN NOT NULL DEFAULT 0",
        "loss_fee": "FLOAT NOT NULL DEFAULT 0",
        "loss_paid": "BOOLEAN NOT NULL DEFAULT 0",
    },
}


def upgrade_legacy_sqlite_schema():
    if db.engine.dialect.name != "sqlite":
        return

    with db.engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        for table_name, upgrades in SQLITE_COLUMN_UPGRADES.items():
            if table_name not in tables:
                continue

            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in upgrades.items():
                if column_name not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {definition}"
                    )
