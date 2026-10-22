import unittest

from werkzeug.security import check_password_hash, generate_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.user_record import UserRecord


class AuthRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        })
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_registration_persists_a_hashed_password_and_logs_in(self):
        response = self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/patron")
        record = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        self.assertTrue(check_password_hash(record.password_hash, "StrongPass1!"))
        self.assertNotEqual(record.password_hash, "StrongPass1!")
        with self.client.session_transaction() as user_session:
            self.assertEqual(user_session["user_id"], record.user_id)
            self.assertEqual(user_session["role"], "patron")
        self.assertIn(b"Welcome, reader", self.client.get("/patron").data)

        self.client.post("/logout")
        login_response = self.client.post(
            "/login",
            data={"username": "reader", "password": "StrongPass1!"},
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.location, "/")
        landing_response = self.client.get("/")
        self.assertEqual(landing_response.status_code, 200)
        self.assertIn(b"Hi, reader", landing_response.data)
        self.assertIn(b"Log out", landing_response.data)

    def test_registered_patron_can_sign_in_with_email(self):
        self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )
        self.client.post("/logout")

        response = self.client.post(
            "/login",
            data={"username": "READER@example.com", "password": "StrongPass1!"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")

    def test_signup_page_has_patron_only_form_and_page_turn_link(self):
        response = self.client.get("/register")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-book-stage', response.data)
        self.assertIn(b'data-book-trigger', response.data)
        self.assertIn(b'id="email"', response.data)
        self.assertIn(b'data-page-turn="previous"', response.data)
        self.assertNotIn(b'name="role"', response.data)
        self.assertNotIn(b'name="staff_code"', response.data)

    def test_signup_validation_error_reopens_book_and_preserves_nonsecret_fields(self):
        response = self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "weak",
                "confirm_password": "weak",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b'class="book-login-stage is-open"', response.data)
        self.assertIn(b'value="reader@example.com"', response.data)
        self.assertIn(b'value="reader"', response.data)
        self.assertNotIn(b'value="weak"', response.data)

    def test_registration_ignores_forged_librarian_role(self):
        response = self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
                "role": "librarian",
                "staff_code": "anything",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/patron")
        record = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        self.assertEqual(record.role, "patron")

    def test_manually_created_librarian_can_log_in_and_open_dashboard(self):
        record = UserRecord(
            email="librarian@example.com",
            username="librarian",
            password_hash=generate_password_hash("StrongPass1!"),
            role="librarian",
        )
        db.session.add(record)
        db.session.commit()

        response = self.client.post(
            "/login",
            data={"username": "librarian", "password": "StrongPass1!"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")
        self.assertEqual(self.client.get("/librarian").status_code, 200)
        self.assertIn(b"manage the library", self.client.get("/librarian").data)

    def test_users_cannot_open_another_role_dashboard(self):
        self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
                "role": "patron",
            },
        )

        self.assertEqual(self.client.get("/librarian").status_code, 403)

    def test_login_rejects_wrong_password(self):
        self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )

        response = self.client.post(
            "/login",
            data={"username": "reader", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Invalid username or password.", response.data)
        self.assertIn(b'class="book-login-stage is-open"', response.data)
        self.assertIn(b'aria-hidden="false"', response.data)

    def test_first_time_sign_in_error_reveals_signup_link_and_keeps_username(self):
        response = self.client.post(
            "/login",
            data={"username": "new-reader", "password": "some-password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn(b'aria-hidden="false"', response.data)
        self.assertIn(b'href="/register" data-page-turn="next">Create an account</a>', response.data)
        self.assertIn(b'value="new-reader"', response.data)

    def test_deactivated_account_cannot_log_in(self):
        self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )
        record = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        record.active = False
        db.session.commit()
        self.client.post("/logout")

        response = self.client.post(
            "/login",
            data={"username": "reader", "password": "StrongPass1!"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"account has been deactivated", response.data)

    def test_registration_rejects_duplicate_username(self):
        form_data = {
            "email": "reader@example.com",
            "username": "reader",
            "password": "StrongPass1!",
            "confirm_password": "StrongPass1!",
        }
        self.client.post("/register", data=form_data)

        response = self.client.post(
            "/register",
            data={
                **form_data,
                "email": "another@example.com",
                "username": "READER",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"username is taken", response.data)

    def test_dashboard_requires_authentication_and_logout_clears_session(self):
        self.assertEqual(self.client.get("/patron").status_code, 302)
        self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )

        response = self.client.post("/logout")

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as user_session:
            self.assertNotIn("user_id", user_session)


if __name__ == "__main__":
    unittest.main()
