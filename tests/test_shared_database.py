import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models import BookRecord, GenreRecord, UserRecord
from backend.app.services.catalog_seed_service import CatalogSeedService


class CatalogSeedServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_seed_copies_catalog_repeatedly_without_users(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "source.sqlite"
            source = sqlite3.connect(source_path)
            try:
                source.executescript(
                    "CREATE TABLE genres (genre_id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
                    "CREATE TABLE books ("
                    "book_id INTEGER PRIMARY KEY, kind VARCHAR(30) NOT NULL, "
                    "title VARCHAR(250) NOT NULL, author VARCHAR(160) NOT NULL, "
                    "genre VARCHAR(100) NOT NULL, description TEXT NOT NULL, "
                    "cover VARCHAR(255), available BOOLEAN NOT NULL, catalog BOOLEAN NOT NULL);"
                    "INSERT INTO genres VALUES (3, 'Mystery');"
                    "INSERT INTO books VALUES "
                    "(7, 'standard', 'Shared Book', 'A. Writer', 'Mystery', '', NULL, 1, 1);"
                )
            finally:
                source.close()

            service = CatalogSeedService()
            self.assertEqual(service.seed_from_sqlite(source_path), {"genres": 1, "books": 1})
            self.assertEqual(service.seed_from_sqlite(source_path), {"genres": 1, "books": 1})

            self.assertEqual(db.session.query(GenreRecord).count(), 1)
            self.assertEqual(db.session.query(BookRecord).count(), 1)
            self.assertEqual(db.session.query(UserRecord).count(), 0)
            self.assertEqual(db.session.get(BookRecord, 7).title, "Shared Book")
