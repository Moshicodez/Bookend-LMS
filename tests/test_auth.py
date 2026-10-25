import re
import unittest

from werkzeug.security import check_password_hash

from backend.app import create_app
from backend.app.extensions import db
from backend.app.models.book_record import BookRecord
from backend.app.models.user_record import UserRecord
from backend.app.services.auth_service import AuthService


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

    def post(self, path, data=None):
        page = self.client.get("/login")
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
        form_data = dict(data or {})
        form_data.setdefault("csrf_token", token)
        return self.client.post(path, data=form_data)

    def register_account(self, email="reader@example.com", username="reader"):
        response = self.post(
            "/register",
            data={
                "email": email,
                "username": username,
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.last_registration_response = response
        return db.session.execute(
            db.select(UserRecord).where(UserRecord.username == username)
        ).scalar_one()

    def login(self, username="reader", password="StrongPass1!"):
        return self.post(
            "/login",
            data={"username": username, "password": password},
        )

    def test_post_requires_a_csrf_token(self):
        response = self.client.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"CSRF token is missing or invalid", response.data)
        self.assertEqual(db.session.scalar(db.select(db.func.count(UserRecord.user_id))), 0)

    def test_login_page_has_csrf_tokens_on_every_post_form(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b'name="csrf_token"'), 2)

    def test_registration_creates_patron_and_requires_valid_email_syntax(self):
        record = self.register_account()

        self.assertEqual(record.role, "patron")
        self.assertTrue(check_password_hash(record.password_hash, "StrongPass1!"))
        self.assertNotEqual(record.password_hash, "StrongPass1!")
        self.assertIn(
            b"Account created. Please sign in.",
            self.last_registration_response.data,
        )
        self.assertIn(b'class="book-login-stage is-open"', self.last_registration_response.data)

        invalid = self.post(
            "/register",
            data={
                "email": "not-an-email",
                "username": "invalid",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
            },
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn(b"Please enter a valid email address", invalid.data)
        self.assertIsNone(
            db.session.execute(
                db.select(UserRecord).where(UserRecord.username == "invalid")
            ).scalar_one_or_none()
        )

    def test_registration_does_not_allow_role_escalation(self):
        response = self.post(
            "/register",
            data={
                "email": "reader@example.com",
                "username": "reader",
                "password": "StrongPass1!",
                "confirm_password": "StrongPass1!",
                "role": "librarian",
            },
        )

        self.assertEqual(response.status_code, 200)
        record = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "reader")
        ).scalar_one()
        self.assertEqual(record.role, "patron")

    def test_signup_route_validates_password_length_and_confirmation(self):
        short_password = self.post(
            "/signup",
            data={
                "email": "short@example.com",
                "username": "shortreader",
                "password": "Short1!",
                "confirm_password": "Short1!",
            },
        )
        self.assertEqual(short_password.status_code, 400)
        self.assertIn(b"Password must be at least 8 characters.", short_password.data)
        self.assertIn(b'id="password-error"', short_password.data)

        mismatched_password = self.post(
            "/signup",
            data={
                "email": "mismatch@example.com",
                "username": "mismatchreader",
                "password": "StrongPass1!",
                "confirm_password": "DifferentPass2!",
            },
        )
        self.assertEqual(mismatched_password.status_code, 400)
        self.assertIn(b"Passwords don&#39;t match.", mismatched_password.data)
        self.assertIn(b'id="confirm-password-error"', mismatched_password.data)

        self.assertEqual(
            db.session.scalar(db.select(db.func.count(UserRecord.user_id))),
            0,
        )

    def test_user_can_log_in_with_email_and_reach_landing_page(self):
        self.register_account()

        response = self.login("READER@example.com")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")
        landing = self.client.get("/")
        self.assertEqual(landing.status_code, 200)
        self.assertIn(b"Hi, reader", landing.data)
        self.assertIn(b"Log out", landing.data)

    def test_login_rejects_wrong_password_and_deactivated_user(self):
        record = self.register_account()
        wrong_password = self.login(password="wrong-password")
        self.assertEqual(wrong_password.status_code, 401)
        self.assertIn(b"Invalid username or password", wrong_password.data)

        record.active = False
        db.session.commit()
        deactivated = self.login()
        self.assertEqual(deactivated.status_code, 403)
        self.assertIn(b"account has been deactivated", deactivated.data)

    def test_change_password_requires_current_password_and_updates_hash(self):
        self.register_account()
        self.assertEqual(self.login().status_code, 302)

        invalid = self.post(
            "/change-password",
            data={
                "current_password": "wrong-password",
                "password": "NewStrongPass2!",
                "confirm_password": "NewStrongPass2!",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertIn(b"Current password is incorrect", invalid.data)

        updated = self.post(
            "/change-password",
            data={
                "current_password": "StrongPass1!",
                "password": "NewStrongPass2!",
                "confirm_password": "NewStrongPass2!",
            },
        )
        self.assertEqual(updated.status_code, 200)
        password_hash = db.session.execute(
            db.select(UserRecord.password_hash).where(UserRecord.username == "reader")
        ).scalar_one()
        self.assertTrue(check_password_hash(password_hash, "NewStrongPass2!"))

    def test_create_librarian_cli_creates_active_account(self):
        result = self.app.test_cli_runner().invoke(
            args=["create-librarian"],
            input=(
                "librarian\n"
                "librarian@example.com\n"
                "StrongPass1!\n"
                "StrongPass1!\n"
            ),
        )

        self.assertEqual(result.exit_code, 0, result.output)
        record = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == "librarian")
        ).scalar_one()
        self.assertEqual(record.role, "librarian")
        self.assertTrue(record.active)
        self.assertEqual(self.login("librarian").status_code, 302)

    def test_create_librarian_cli_rejects_weak_password(self):
        result = self.app.test_cli_runner().invoke(
            args=["create-librarian"],
            input=(
                "librarian\n"
                "librarian@example.com\n"
                "weak\n"
                "weak\n"
            ),
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Password too weak.", result.output)
        self.assertIsNone(
            db.session.execute(
                db.select(UserRecord).where(UserRecord.username == "librarian")
            ).scalar_one_or_none()
        )

    def test_seed_demo_cli_imports_books_and_skips_existing_titles(self):
        runner = self.app.test_cli_runner()

        first_run = runner.invoke(args=["seed-demo"])
        second_run = runner.invoke(args=["seed-demo"])

        self.assertEqual(first_run.exit_code, 0, first_run.output)
        self.assertIn("Added 24 demo books.", first_run.output)
        self.assertEqual(second_run.exit_code, 0, second_run.output)
        self.assertIn("Added 0 demo books.", second_run.output)
        self.assertEqual(
            db.session.scalar(db.select(db.func.count()).select_from(BookRecord)),
            24,
        )

    def test_reset_user_password_cli_changes_password(self):
        self.register_account()

        result = self.app.test_cli_runner().invoke(
            args=["reset-user-password", "reader@example.com"],
            input="NewStrongPass2!\nNewStrongPass2!\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.login(password="NewStrongPass2!").status_code, 302)

    def test_signup_page_has_patron_only_form_and_extends_base(self):
        response = self.client.get("/signup")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-book-stage', response.data)
        self.assertIn(b'data-book-trigger', response.data)
        self.assertIn(b'id="email"', response.data)
        self.assertIn(b'action="/signup"', response.data)
        self.assertIn(b'href="/signup" data-page-turn="next"', response.data)
        self.assertIn(b'autocomplete="current-password"', response.data)
        self.assertIn(b'autocomplete="new-password"', response.data)
        self.assertIn(b'id="reg-confirm"', response.data)
        self.assertIn(b'data-password-toggle="reg-confirm"', response.data)
        self.assertIn(b'At least 8 characters.', response.data)
        self.assertIn(b'Having trouble signing in? Forgot your password?', response.data)
        self.assertEqual(response.data.count(b'class="brand form-brand"'), 1)
        self.assertNotIn(b'name="role"', response.data)
        self.assertNotIn(b"forgot-password", response.data)
        self.assertIn(b"css/style.css", response.data)

    def test_dashboard_authentication_and_logout(self):
        self.assertEqual(self.client.get("/patron").status_code, 302)
        self.register_account()
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.get("/patron").status_code, 200)

        response = self.post("/logout")

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as user_session:
            self.assertNotIn("user_id", user_session)


if __name__ == "__main__":
    unittest.main()
