import random

from sqlalchemy import inspect, text

from .extensions import db


SQLITE_COLUMN_UPGRADES = {
    "books": {
        "kind": "VARCHAR(30) NOT NULL DEFAULT 'standard'",
        "cover": "VARCHAR(255)",
        "archived_at": "DATETIME",
    },
    "loans": {
        "fee_paid": "BOOLEAN NOT NULL DEFAULT 0",
        "lost": "BOOLEAN NOT NULL DEFAULT 0",
        "loss_fee": "FLOAT NOT NULL DEFAULT 0",
        "loss_paid": "BOOLEAN NOT NULL DEFAULT 0",
    },
}


def upgrade_legacy_sqlite_schema():
    if db.engine.dialect.name == "sqlite":
        _upgrade_sqlite_schema()
    _upgrade_loss_fee_amount()
    _upgrade_fee_payments()


def _upgrade_fee_payments():
    if db.engine.dialect.name != "sqlite":
        return
    existing_tables = set(inspect(db.engine).get_table_names())
    if not {"loans", "users"}.issubset(existing_tables):
        return
    from .models.fee_payment_record import FeePaymentRecord

    FeePaymentRecord.__table__.create(db.engine, checkfirst=True)
    with db.engine.begin() as connection:
        columns = {
            column["name"] for column in inspect(connection).get_columns("loans")
        }
        if not {"fee_paid", "loss_paid", "loss_fee", "due_date", "loan_id"}.issubset(columns):
            return
        connection.execute(
            text(
                """
                INSERT INTO fee_payments
                    (loan_id, fee_type, amount, confirmed_by, confirmed_at, note)
                SELECT loans.loan_id, 'late',
                    ROUND(MAX(0, julianday(COALESCE(returned_at, CURRENT_DATE))
                        - julianday(due_date)) * 0.5, 2),
                    NULL, CURRENT_TIMESTAMP, 'Imported'
                FROM loans
                WHERE fee_paid = 1
                  AND NOT EXISTS (
                    SELECT 1 FROM fee_payments
                    WHERE fee_payments.loan_id = loans.loan_id
                      AND fee_payments.fee_type = 'late'
                      AND fee_payments.voided_at IS NULL
                  )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO fee_payments
                    (loan_id, fee_type, amount, confirmed_by, confirmed_at, note)
                SELECT loans.loan_id, 'loss',
                    CASE WHEN loss_fee > 0 THEN loss_fee ELSE 2500.0 END,
                    NULL, CURRENT_TIMESTAMP, 'Imported'
                FROM loans
                WHERE loss_paid = 1
                  AND NOT EXISTS (
                    SELECT 1 FROM fee_payments
                    WHERE fee_payments.loan_id = loans.loan_id
                      AND fee_payments.fee_type = 'loss'
                      AND fee_payments.voided_at IS NULL
                  )
                """
            )
        )


def _upgrade_sqlite_schema():
    with db.engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        for table_name in ("books", "loans"):
            if table_name not in tables:
                continue
            columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, definition in SQLITE_COLUMN_UPGRADES[table_name].items():
                if column_name not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
                    )

        if "books" not in tables:
            return

        book_columns = {
            column["name"] for column in inspect(connection).get_columns("books")
        }
        added_total_copies = "total_copies" not in book_columns
        if added_total_copies:
            connection.exec_driver_sql(
                "ALTER TABLE books ADD COLUMN total_copies "
                "INTEGER NOT NULL DEFAULT 1 CHECK (total_copies >= 0)"
            )
            if "total_stock" in book_columns:
                connection.exec_driver_sql(
                    "UPDATE books SET total_copies = total_stock "
                    "WHERE total_stock IS NOT NULL AND total_stock >= 0"
                )
            else:
                _backfill_book_copies(connection, tables)

        if "loans" in tables:
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


def _backfill_book_copies(connection, tables):
    rows = connection.exec_driver_sql(
        "SELECT book_id FROM books WHERE total_copies = 1"
    ).fetchall()
    active_counts = {}
    ready_counts = {}
    if "loans" in tables:
        loan_columns = {
            column["name"] for column in inspect(connection).get_columns("loans")
        }
        if {"book_id", "loan_id", "returned_at"}.issubset(loan_columns):
            active_counts = dict(
                connection.exec_driver_sql(
                    "SELECT book_id, COUNT(loan_id) FROM loans "
                    "WHERE returned_at IS NULL GROUP BY book_id"
                ).fetchall()
            )
    if "reservations" in tables:
        reservation_columns = {
            column["name"]
            for column in inspect(connection).get_columns("reservations")
        }
        if {"book_id", "reservation_id", "status"}.issubset(reservation_columns):
            ready_counts = dict(
                connection.exec_driver_sql(
                    "SELECT book_id, COUNT(reservation_id) FROM reservations "
                    "WHERE status = 'ready' GROUP BY book_id"
                ).fetchall()
            )
    for (book_id,) in rows:
        minimum = max(active_counts.get(book_id, 0) + ready_counts.get(book_id, 0), 1)
        total = max(random.randint(1, 10), minimum)
        connection.exec_driver_sql(
            "UPDATE books SET total_copies = ? WHERE book_id = ?",
            (total, book_id),
        )


def _upgrade_loss_fee_amount():
    with db.engine.begin() as connection:
        inspector = inspect(connection)
        if "loans" not in set(inspector.get_table_names()):
            return
        columns = {column["name"] for column in inspector.get_columns("loans")}
        if not {"loss_fee", "loss_paid"}.issubset(columns):
            return
        connection.execute(
            text(
                "UPDATE loans SET loss_fee = :new_fee "
                "WHERE loss_fee = :old_fee AND loss_paid = :unpaid"
            ),
            {"new_fee": 2500.00, "old_fee": 25.00, "unpaid": False},
        )
