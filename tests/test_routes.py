import unittest

from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book import Book
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

    def register_patron(self, username="reader"):
        return self.client.post(
            "/register",
            data={
                "email": f"{username}@example.com",
                "username": username,
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
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

    def test_catalog_requires_login_and_renders_books_for_patron(self):
        self.assertEqual(self.client.get("/books/").status_code, 302)
        self.register_patron()
        BookRepository().create(Book(None, "A Book", "An Author", "", ""))

        response = self.client.get("/books/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"A Book", response.data)

    def test_patron_can_borrow_and_return_a_book(self):
        self.register_patron()
        book = BookRepository().create(Book(None, "Available", "Writer", "", ""))

        borrowed = self.client.post(f"/loans/borrow/{book.book_id}")
        self.assertEqual(borrowed.status_code, 302)
        self.assertEqual(
            self.client.get(f"/books/{book.book_id}").status_code,
            200,
        )
        loans_page = self.client.get("/loans/")
        self.assertEqual(loans_page.status_code, 200)
        self.assertIn(b"Currently on loan", loans_page.data)

        returned = self.client.post(f"/loans/return/{book.book_id}")
        self.assertEqual(returned.status_code, 302)
        self.assertTrue(BookRepository().find_book(book.book_id).available)

    def test_librarian_can_add_book_and_manage_members(self):
        self.register_patron()
        patron = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        self.client.post("/logout")
        self.create_librarian()
        self.client.post(
            "/login",
            data={"username": "staff", "password": "StrongPass1!"},
        )

        created = self.client.post(
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

        self.client.post(f"/members/{patron.user_id}/toggle")
        updated = db.session.get(UserRecord, patron.user_id)
        self.assertFalse(updated.active)

    def test_patron_cannot_access_librarian_routes_or_add_books(self):
        self.register_patron()

        self.assertEqual(self.client.get("/members/").status_code, 403)
        response = self.client.post(
            "/books/new",
            data={"title": "Forbidden", "author": "Writer"},
        )
        self.assertEqual(response.status_code, 403)

    def test_route_rejects_reference_book_checkout(self):
        self.register_patron()
        reference = BookRepository().create(
            Book.create("reference", None, "Reference", "Writer", "", "")
        )

        response = self.client.post(f"/loans/borrow/{reference.book_id}")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Reference books can only be read in the library.", response.data)


if __name__ == "__main__":
    unittest.main()