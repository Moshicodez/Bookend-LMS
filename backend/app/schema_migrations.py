from sqlalchemy import inspect

from .extensions import db


SQLITE_COLUMN_UPGRADES = {
    "books": {
        "kind": "VARCHAR(30) NOT NULL DEFAULT 'standard'",
        "cover": "VARCHAR(255)",
        "archived_at": "DATETIME",
        "total_copies": "INTEGER NOT NULL DEFAULT 1 CHECK (total_copies >= 0)",
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
        book_copy_count_added = False

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
                    if table_name == "books" and column_name == "total_copies":
                        book_copy_count_added = True

        if book_copy_count_added and "loans" in tables:
            loan_columns = {
                column["name"] for column in inspect(connection).get_columns("loans")
            }
            if {"lost", "returned_at", "book_id"}.issubset(loan_columns):
                connection.exec_driver_sql(
                    """
                    UPDATE books
                    SET total_copies = 0
                    WHERE available = 0
                      AND catalog = 0
                      AND EXISTS (
                          SELECT 1 FROM loans
                          WHERE loans.book_id = books.book_id
                            AND loans.lost = 1
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM loans
                          WHERE loans.book_id = books.book_id
                            AND loans.returned_at IS NULL
                      )
                    """
                )
