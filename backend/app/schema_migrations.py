import random

from sqlalchemy import inspect, text

from .extensions import db
from .constants import UNCATEGORIZED


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
        _upgrade_sqlite_nullable_references()
    _upgrade_loss_fee_amount()
    _upgrade_fee_payments()


def _upgrade_sqlite_nullable_references():
    if db.engine.dialect.name != "sqlite":
        return
    raw_connection = db.engine.raw_connection()
    cursor = raw_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN")
        tables = {
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "books" in tables:
            book_info = cursor.execute("PRAGMA table_info(books)").fetchall()
            genre_column = next(
                (column for column in book_info if column[1] == "genre"),
                None,
            )
            if genre_column and genre_column[3]:
                columns = {column[1] for column in book_info}
                cursor.execute(
                    """
                    CREATE TABLE books_replacement (
                        book_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind VARCHAR(30) NOT NULL DEFAULT 'standard',
                        title VARCHAR(250) NOT NULL,
                        author VARCHAR(160) NOT NULL,
                        genre VARCHAR(100),
                        description TEXT NOT NULL DEFAULT '',
                        cover VARCHAR(255),
                        available BOOLEAN NOT NULL DEFAULT 1,
                        catalog BOOLEAN NOT NULL DEFAULT 1,
                        archived_at DATETIME,
                        total_copies INTEGER NOT NULL DEFAULT 1
                            CHECK (total_copies >= 0),
                        CONSTRAINT valid_book_kind
                            CHECK (kind IN ('standard', 'new_release', 'reference'))
                    )
                    """
                )
                target_columns = (
                    "book_id", "kind", "title", "author", "genre",
                    "description", "cover", "available", "catalog",
                    "archived_at", "total_copies",
                )
                defaults = {
                    "kind": "'standard'",
                    "genre": "''",
                    "description": "''",
                    "cover": "NULL",
                    "available": "1",
                    "catalog": "1",
                    "archived_at": "NULL",
                    "total_copies": "1",
                }
                select_columns = [
                    name if name in columns else defaults[name]
                    for name in target_columns
                ]
                cursor.execute(
                    "INSERT INTO books_replacement ("
                    + ", ".join(target_columns)
                    + ") SELECT "
                    + ", ".join(select_columns)
                    + " FROM books"
                )
                cursor.execute("DROP TABLE books")
                cursor.execute("ALTER TABLE books_replacement RENAME TO books")

        if "loans" in tables:
            loan_info = cursor.execute("PRAGMA table_info(loans)").fetchall()
            book_column = next(
                (column for column in loan_info if column[1] == "book_id"),
                None,
            )
            book_fk = next(
                (
                    row for row in cursor.execute("PRAGMA foreign_key_list(loans)")
                    if row[3] == "book_id"
                ),
                None,
            )
            loan_columns = {column[1] for column in loan_info}
            if (
                (book_column and book_column[3])
                or not {"book_title", "book_author"}.issubset(loan_columns)
                or (book_fk and book_fk[6].upper() != "SET NULL")
            ):
                cursor.execute(
                    """
                    CREATE TABLE loans_replacement (
                        loan_id INTEGER PRIMARY KEY,
                        patron_id INTEGER NOT NULL
                            REFERENCES users(user_id) ON DELETE RESTRICT,
                        book_id INTEGER REFERENCES books(book_id) ON DELETE SET NULL,
                        book_title VARCHAR(250) NOT NULL DEFAULT '',
                        book_author VARCHAR(160) NOT NULL DEFAULT '',
                        borrowed_at DATE NOT NULL,
                        due_date DATE NOT NULL,
                        returned_at DATE,
                        fee_paid BOOLEAN NOT NULL DEFAULT 0,
                        lost BOOLEAN NOT NULL DEFAULT 0,
                        loss_fee FLOAT NOT NULL DEFAULT 0,
                        loss_paid BOOLEAN NOT NULL DEFAULT 0
                    )
                    """
                )
                value = lambda name, fallback: name if name in loan_columns else fallback
                book_id = value("book_id", "NULL")
                title = (
                    "COALESCE(loans.book_title, books.title, '')"
                    if "book_title" in loan_columns
                    else "COALESCE(books.title, '')"
                )
                author = (
                    "COALESCE(loans.book_author, books.author, '')"
                    if "book_author" in loan_columns
                    else "COALESCE(books.author, '')"
                )
                fields = (
                    "loan_id", "patron_id", "book_id", "book_title",
                    "book_author", "borrowed_at", "due_date", "returned_at",
                    "fee_paid", "lost", "loss_fee", "loss_paid",
                )
                selections = [
                    title if field == "book_title"
                    else author if field == "book_author"
                    else f"loans.{field}" if field in loan_columns
                    else "0" if field in {
                        "fee_paid", "lost", "loss_fee", "loss_paid"
                    } else "NULL"
                    for field in fields
                ]
                cursor.execute(
                    "INSERT INTO loans_replacement ("
                    + ", ".join(fields)
                    + ") SELECT "
                    + ", ".join(selections)
                    + " FROM loans LEFT JOIN books ON books.book_id = loans.book_id"
                )
                cursor.execute("DROP TABLE loans")
                cursor.execute("ALTER TABLE loans_replacement RENAME TO loans")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_loans_book_id ON loans (book_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_loans_patron_id ON loans (patron_id)"
                )

        if "genres" in tables and "books" in tables:
            cursor.execute(
                """
                UPDATE books SET genre = ''
                WHERE genre IS NOT NULL
                  AND lower(trim(genre)) = ?
                """,
                (UNCATEGORIZED.casefold(),),
            )
            reserved_genre = UNCATEGORIZED.casefold().replace("'", "''")
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS genres_reserved_name_insert
                BEFORE INSERT ON genres
                WHEN lower(trim(NEW.name)) = '{reserved_genre}'
                BEGIN
                    SELECT RAISE(ABORT, 'reserved virtual genre');
                END
                """
            )
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS genres_reserved_name_update
                BEFORE UPDATE OF name ON genres
                WHEN lower(trim(NEW.name)) = '{reserved_genre}'
                BEGIN
                    SELECT RAISE(ABORT, 'reserved virtual genre');
                END
                """
            )
            cursor.execute(
                """
                DELETE FROM genres
                WHERE lower(trim(name)) = ?
                """,
                (UNCATEGORIZED.casefold(),),
            )
        cursor.execute("COMMIT")
    except Exception:
        cursor.execute("ROLLBACK")
        raise
    finally:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        raw_connection.close()
    from .models.basket_record import BasketRecord

    BasketRecord.__table__.create(db.engine, checkfirst=True)


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
