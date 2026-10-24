import unittest
import html
import io
import re
import tempfile
from datetime import date
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
from backend.app.models.book_record import BookRecord
from backend.app.models.user_record import UserRecord
from backend.app.repositories.book_repository import BookRepository


class BackendRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "routes-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def post(self, path, data=None):
        page = self.client.get("/login")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        form_data = dict(data or {})
        form_data.setdefault("csrf_token", token)
        return self.client.post(path, data=form_data)

    def register_patron(self, username="reader"):
        response = self.post(
            "/register",
            data={
                "email": f"{username}@example.com",
                "username": username,
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )
        self.assertEqual(response.status_code, 200)
        return self.post(
            "/login",
            data={"username": username, "password": "StrongPass1!"},
        )

    def create_librarian(self):
        record = UserRecord(
            email="staff@example.com",
            username="staff",
            password_hash=generate_password_hash("StrongPass1!"),
            role="librarian",
        )
        db.session.add(record)
        db.session.commit()
        return record

    def test_catalog_is_public_and_renders_books_for_patron(self):
        self.assertEqual(self.client.get("/books/").status_code, 200)
        self.register_patron()
        BookRepository().create(Book(None, "A Book", "An Author", "", ""))

        response = self.client.get("/books/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"A Book", response.data)

    def test_patron_can_borrow_and_return_a_book(self):
        self.register_patron()
        book = BookRepository().create(Book(None, "Available", "Writer", "", ""))

        borrowed = self.post(f"/loans/borrow/{book.book_id}")
        self.assertEqual(borrowed.status_code, 302)
        self.assertEqual(
            self.client.get(f"/books/{book.book_id}").status_code,
            200,
        )
        loans_page = self.client.get("/loans/")
        self.assertEqual(loans_page.status_code, 200)
        self.assertIn(b"On loan", loans_page.data)

        returned = self.post(f"/loans/return/{book.book_id}")
        self.assertEqual(returned.status_code, 302)
        self.assertTrue(BookRepository().find_book(book.book_id).available)

    def test_librarian_can_add_book_and_manage_members(self):
        self.register_patron()
        patron = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        self.post("/logout")
        self.create_librarian()
        self.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )

        created = self.post(
            "/books/new",
            data={
                "title": "New catalog book",
                "author": "Writer",
                "genre": "Fiction",
                "description": "",
                "kind": "new_release",
            },
        )
        self.assertEqual(created.status_code, 302)
        self.assertEqual(self.client.get("/members/").status_code, 200)

        self.post(f"/members/{patron.user_id}/toggle")
        updated = db.session.get(UserRecord, patron.user_id)
        self.assertFalse(updated.active)

    def test_librarian_can_upload_jpg_cover_for_book(self):
        upload_directory = tempfile.TemporaryDirectory()
        self.addCleanup(upload_directory.cleanup)
        self.app.config["COVER_UPLOAD_FOLDER"] = upload_directory.name
        self.create_librarian()
        self.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )

        response = self.post(
            "/books/new",
            data={
                "title": "Cover upload",
                "author": "Writer",
                "genre": "History",
                "description": "",
                "kind": "standard",
                "cover": (io.BytesIO(b"\xff\xd8\xffjpeg-data"), "../../cover.jpg"),
            },
        )

        self.assertEqual(response.status_code, 302)
        record = db.session.execute(
            db.select(BookRecord).where(BookRecord.title == "Cover upload")
        ).scalar_one()
        self.assertRegex(record.cover, r"^[a-f0-9]{32}\.jpg$")
        self.assertEqual(
            (Path(upload_directory.name) / record.cover).read_bytes(),
            b"\xff\xd8\xffjpeg-data",
        )

    def test_librarian_can_reset_patron_password_once(self):
        self.register_patron()
        patron = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        self.post("/logout")
        self.create_librarian()
        self.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )

        response = self.post(f"/members/{patron.user_id}/reset-password")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Temporary password", response.data)
        temporary_password = html.unescape(
            re.search(rb"<code>(.*?)</code>", response.data).group(1).decode()
        )
        self.assertEqual(len(temporary_password), 16)
        self.assertEqual(
            self.client.get("/members/").data.count(temporary_password.encode()),
            0,
        )
        self.assertTrue(check_password_hash(patron.password_hash, temporary_password))

    def test_patron_cannot_reset_member_password(self):
        self.register_patron()
        patron = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()

        response = self.post(f"/members/{patron.user_id}/reset-password")

        self.assertEqual(response.status_code, 403)

    def test_patron_cannot_access_librarian_routes_or_add_books(self):
        self.register_patron()

        self.assertEqual(self.client.get("/members/").status_code, 403)
        response = self.post(
            "/books/new",
            data={"title": "Forbidden", "author": "Writer"},
        )
        self.assertEqual(response.status_code, 403)

    def test_librarian_can_restore_archived_book(self):
        self.create_librarian()
        self.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )
        book = BookRepository().create(Book(None, "Archived title", "Writer", "", ""))
        self.post(f"/books/{book.book_id}/archive")

        archived = self.client.get("/books/archived")
        self.assertEqual(archived.status_code, 200)
        self.assertIn(b"Archived title", archived.data)
        restored = self.post(f"/books/{book.book_id}/restore")

        self.assertEqual(restored.status_code, 302)
        self.assertEqual(restored.location, "/books/archived")
        self.assertNotIn(b"Archived title", self.client.get("/books/archived").data)
        self.assertIn(b"Archived title", self.client.get("/books/").data)

    def test_patron_cannot_view_or_restore_archived_books(self):
        self.register_patron()
        book = BookRepository().create(Book(None, "Archived title", "Writer", "", ""))
        self.post("/logout")
        self.create_librarian()
        self.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )
        self.post(f"/books/{book.book_id}/archive")
        self.post("/logout")
        self.register_patron("second")

        self.assertEqual(self.client.get("/books/archived").status_code, 403)
        self.assertEqual(self.post(f"/books/{book.book_id}/restore").status_code, 403)

    def test_members_search_and_create_patron(self):
        self.create_librarian()
        self.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )

        created = self.post(
            "/members/new",
            data={
                "username": "searchreader",
                "email": "search@example.com",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )
        self.assertEqual(created.status_code, 302)

        by_username = self.client.get("/members/?q=searchread")
        by_email = self.client.get("/members/?q=search@example")
        self.assertIn(b"searchreader", by_username.data)
        self.assertIn(b"searchreader", by_email.data)
        self.assertNotIn(b">reader</a>", by_username.data)

        record = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "searchreader")
        ).scalar_one()
        self.assertEqual(record.role, "patron")
        self.assertTrue(check_password_hash(record.password_hash, "StrongPass1!"))

    def test_member_detail_shows_loan_history_and_fees(self):
        self.register_patron()
        patron = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        book = BookRepository().create(Book(None, "Loan history title", "Writer", "", ""))
        from backend.app.repositories.loan_repository import LoanRepository

        LoanRepository().create_loan(
            patron.user_id,
            book.book_id,
            date(2026, 1, 1),
            date(2026, 1, 15),
        )
        self.post("/logout")
        self.create_librarian()
        self.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )

        response = self.client.get(f"/members/{patron.user_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Loan history title", response.data)
        self.assertIn(b"Outstanding:", response.data)
        self.assertIn(b"Unpaid", response.data)

    def test_route_rejects_reference_book_checkout(self):
        self.register_patron()
        reference = BookRepository().create(
            Book.create("reference", None, "Reference", "Writer", "", "")
        )

        response = self.post(f"/loans/borrow/{reference.book_id}")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Reference books can only be read in the library.", response.data)


if __name__ == "__main__":
    unittest.main()