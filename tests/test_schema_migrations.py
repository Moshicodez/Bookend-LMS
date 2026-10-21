import unittest
from datetime import date, timedelta

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book_record import BookRecord
from backend.app.models.user_record import UserRecord
from backend.app.schema_migrations import upgrade_legacy_sqlite_schema


class LegacySchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "migration-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()

        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE books ("
                "book_id INTEGER PRIMARY KEY, "
                "title VARCHAR(200) NOT NULL, "
                "author VARCHAR(120) NOT NULL, "
                "genre VARCHAR(80), "
                "description TEXT, "
                "available BOOLEAN NOT NULL, "
                "catalog BOOLEAN NOT NULL)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE loans ("
                "loan_id INTEGER PRIMARY KEY, "
                "patron_id INTEGER NOT NULL, "
                "book_id INTEGER NOT NULL, "
                "borrowed_at DATE NOT NULL, "
                "due_date DATE NOT NULL, "
                "returned_at DATE, "
                "late_fee FLOAT NOT NULL)"
            )

        db.create_all()
        db.session.add(
            UserRecord(
                email="reader@example.com",
                username="reader",
                password_hash=generate_password_hash("StrongPass1!"),
                role="patron",
            )
        )
        db.session.commit()
        db.session.execute(
            text(
                "INSERT INTO books "
                "(book_id, title, author, genre, description, available, catalog) "
                "VALUES (1, 'Legacy Book', 'A. Writer', 'History', '', 1, 1)"
            )
        )
        db.session.execute(
            text(
                "INSERT INTO loans "
                "(loan_id, patron_id, book_id, borrowed_at, due_date, late_fee) "
                "VALUES (1, 1, 1, :borrowed_at, :due_date, 0)"
            ),
            {
                "borrowed_at": date.today().isoformat(),
                "due_date": (date.today() + timedelta(days=14)).isoformat(),
            },
        )
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_legacy_sqlite_schema_is_upgraded_without_losing_records(self):
        upgrade_legacy_sqlite_schema()
        upgrade_legacy_sqlite_schema()

        book = db.session.get(BookRecord, 1)
        columns = {
            table: {column["name"] for column in inspect(db.engine).get_columns(table)}
            for table in ("books", "loans")
        }

        self.assertEqual(book.title, "Legacy Book")
        self.assertEqual(book.kind, "standard")
        self.assertTrue(
            {"kind"}.issubset(columns["books"])
        )
        self.assertTrue(
            {"fee_paid", "lost", "loss_fee", "loss_paid"}.issubset(columns["loans"])
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Legacy Book", response.data)


if __name__ == "__main__":
    unittest.main()
