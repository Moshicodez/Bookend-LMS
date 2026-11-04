from sqlalchemy import inspect

from .extensions import db


SQLITE_COLUMN_UPGRADES = {
    "books": {
        "kind": "VARCHAR(30) NOT NULL DEFAULT 'standard'",
        "cover": "VARCHAR(255)",
        "total_stock": "INTEGER NOT NULL DEFAULT 1",
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
        stock_added = False

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
                    if table_name == "books" and column_name == "total_stock":
                        stock_added = True

        if stock_added:
            active_count = "0"
            if "loans" in tables:
                loan_columns = {
                    column["name"] for column in inspect(connection).get_columns("loans")
                }
                if {"book_id", "returned_at"}.issubset(loan_columns):
                    lost_filter = " AND loans.lost = 0" if "lost" in loan_columns else ""
                    active_count = (
                        "(SELECT COUNT(*) FROM loans "
                        "WHERE loans.book_id = books.book_id "
                        "AND loans.returned_at IS NULL"
                        f"{lost_filter})"
                    )
            connection.exec_driver_sql(
                "UPDATE books SET total_stock = "
                f"{active_count} + CASE WHEN available = 1 THEN 1 ELSE 0 END"
            )
