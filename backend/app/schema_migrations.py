import random

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

        if "books" in tables:
            book_columns = {column["name"] for column in inspector.get_columns("books")}
            for column_name, definition in SQLITE_COLUMN_UPGRADES["books"].items():
                if column_name not in book_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE books ADD COLUMN {column_name} {definition}"
                    )
                    book_columns.add(column_name)

            books = inspector.get_columns("books")
            book_column_names = {column["name"] for column in books}
            if "total_stock" in book_column_names and "total_copies" in book_column_names:
                connection.exec_driver_sql(
                    "UPDATE books SET total_copies = CASE WHEN total_stock IS NULL THEN 1 ELSE total_stock END WHERE total_copies IS NULL OR total_copies < 0"
                )
            elif "total_stock" in book_column_names and "total_copies" not in book_column_names:
                connection.exec_driver_sql(
                    "ALTER TABLE books ADD COLUMN total_copies INTEGER NOT NULL DEFAULT 1 CHECK (total_copies >= 0)"
                )
                connection.exec_driver_sql(
                    "UPDATE books SET total_copies = CASE WHEN total_stock IS NULL THEN 1 ELSE total_stock END"
                )

            if "total_copies" in book_column_names:
                connection.exec_driver_sql(
                    "UPDATE books SET total_copies = 1 WHERE total_copies IS NULL OR total_copies < 0"
                )

            if "total_copies" in book_column_names:
                rows = connection.exec_driver_sql(
                    "SELECT book_id, total_copies FROM books"
                ).fetchall()
                active_counts = {}
                ready_counts = {}
                if "loans" in tables:
                    active_counts = {
                        book_id: count
                        for book_id, count in connection.exec_driver_sql(
                            "SELECT book_id, COUNT(loan_id) FROM loans WHERE returned_at IS NULL GROUP BY book_id"
                        ).fetchall()
                    }
                if "reservations" in tables:
                    ready_counts = {
                        book_id: count
                        for book_id, count in connection.exec_driver_sql(
                            "SELECT book_id, COUNT(reservation_id) FROM reservations WHERE status = 'ready' GROUP BY book_id"
                        ).fetchall()
                    }
                for book_id, total_copies in rows:
                    if total_copies is None or total_copies < 1:
                        required_min = max(
                            active_counts.get(book_id, 0) + ready_counts.get(book_id, 0),
                            1,
                        )
                        random_total = max(random.randint(1, 10), required_min)
                        connection.exec_driver_sql(
                            "UPDATE books SET total_copies = ? WHERE book_id = ?",
                            (random_total, book_id),
                        )

        for table_name, upgrades in SQLITE_COLUMN_UPGRADES.items():
            if table_name == "books":
                continue
            if table_name not in tables:
                continue

            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in upgrades.items():
                if column_name not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                    )

        if "loans" in tables:
            loan_columns = {column["name"] for column in inspector.get_columns("loans")}
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
