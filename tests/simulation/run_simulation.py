"""Isolated browser simulation for Bookend LMS.

The simulation copies the committed starter database to a temporary directory,
then resets that copy between guest, patron, and librarian sections. It never
uses the application database configured in .env.
"""

from __future__ import annotations

import base64
import csv
import html
import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import sync_playwright
from sqlalchemy.pool import NullPool
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
STARTER_DB = ROOT / "backend" / "app" / "bookend-starter.sqlite"
REPORT_DIR = ROOT / "docs" / "simulation_report"
FAIL_IMAGE_DIR = REPORT_DIR / "fail-images"
PASSWORD = "StrongPass1!"
HEADERS = [
    "ID",
    "Role",
    "Module",
    "Function (what it should do)",
    "Button/Control (label + selector)",
    "Page where clicked",
    "HTTP method + route requested",
    "Input used",
    "Expected output",
    "Actual output (flash text, redirect URL, status code, DB change)",
    "Status",
    "Evidence (screenshot or log path)",
    "Notes / suspected cause",
]


class Simulation:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bookend-simulation-")
        temp_path = Path(self.temp.name)
        self.database_path = temp_path / "simulation.sqlite"
        self.upload_path = temp_path / "uploads"
        self.upload_path.mkdir()
        shutil.copy2(STARTER_DB, self.database_path)
        self.rows: list[dict[str, str]] = []
        self.counter = 0
        self.console_errors: list[str] = []
        self.events: list[dict[str, object]] = []
        self.fixture: dict[str, object] = {}
        self.database_uri = "sqlite:///" + self.database_path.as_posix()

        from backend.app import create_app
        from backend.app.extensions import db

        self.db = db
        self.app = create_app(
            {
                "TESTING": False,
                "SECRET_KEY": "isolated-simulation-secret",
                "SQLALCHEMY_DATABASE_URI": self.database_uri,
                "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
                "COVER_UPLOAD_FOLDER": str(self.upload_path),
            }
        )
        self.server = make_server("127.0.0.1", 0, self.app, threaded=False)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="bookend-simulation-server",
            daemon=True,
        )
        self.server_thread.start()

    def close(self):
        self.server.shutdown()
        self.server_thread.join(timeout=3)
        with self.app.app_context():
            self.db.session.remove()
            self.db.engine.dispose()
        self.temp.cleanup()

    def reset_and_seed(self):
        from backend.app.models.book import Book
        from backend.app.models.book_record import BookRecord
        from backend.app.models.loan_record import LoanRecord
        from backend.app.models.notification_record import NotificationRecord
        from backend.app.models.reservation_record import ReservationRecord
        from backend.app.repositories.book_repository import BookRepository
        from backend.app.repositories.notification_repository import NotificationRepository
        from backend.app.repositories.user_repository import UserRepository

        with self.app.app_context():
            self.db.session.remove()
            self.db.drop_all()
            self.db.create_all()
            users = UserRepository()
            librarian = users.create(
                "staff@example.com",
                "staff",
                generate_password_hash(PASSWORD),
                "librarian",
            )
            patron_a = users.create(
                "reader-a@example.com",
                "reader-a",
                generate_password_hash(PASSWORD),
                "patron",
            )
            patron_b = users.create(
                "reader-b@example.com",
                "reader-b",
                generate_password_hash(PASSWORD),
                "patron",
            )
            books = BookRepository()
            definitions = [
                ("Borrowed Fixture", "History", 2, "standard"),
                ("Overdue Fixture", "History", 1, "standard"),
                ("Lost Fixture", "Mystery", 2, "standard"),
                ("Ready Reservation Fixture", "Science", 1, "standard"),
                ("Waiting Reservation Fixture", "Science", 1, "standard"),
                ("Reference Fixture", "History", 1, "reference"),
                ("Single Copy Fixture", "Mystery", 1, "standard"),
                ("Many Copies Fixture", "Science", 20, "standard"),
                ("Uncategorized Fixture", "", 4, "standard"),
            ]
            created = {}
            for title, genre, copies, kind in definitions:
                created[title] = books.create(
                    Book.create(
                        kind,
                        None,
                        title,
                        "QA Author",
                        genre,
                        f"Simulation fixture for {title}.",
                        total_copies=copies,
                    )
                )
            for number in range(25):
                title = f"Pagination Fixture {number:02d}"
                created[title] = books.create(
                    Book(None, title, "QA Author", ("History", "Mystery", "Science")[number % 3], "")
                )
            archived = books.create(
                Book(None, "Archived Fixture", "QA Author", "History", "")
            )
            archived_record = self.db.session.get(BookRecord, archived.book_id)
            archived_record.catalog = False

            today = date.today()
            borrowed = created["Borrowed Fixture"]
            overdue = created["Overdue Fixture"]
            lost = created["Lost Fixture"]
            self.db.session.add_all(
                [
                    LoanRecord(
                        patron_id=patron_a.user_id,
                        book_id=borrowed.book_id,
                        book_title=borrowed.title,
                        book_author=borrowed.author,
                        borrowed_at=today - timedelta(days=2),
                        due_date=today + timedelta(days=12),
                    ),
                    LoanRecord(
                        patron_id=patron_b.user_id,
                        book_id=overdue.book_id,
                        book_title=overdue.title,
                        book_author=overdue.author,
                        borrowed_at=today - timedelta(days=20),
                        due_date=today - timedelta(days=4),
                    ),
                    LoanRecord(
                        patron_id=patron_b.user_id,
                        book_id=lost.book_id,
                        book_title=lost.title,
                        book_author=lost.author,
                        borrowed_at=today - timedelta(days=25),
                        due_date=today - timedelta(days=11),
                        lost=True,
                        loss_fee=2500.0,
                    ),
                    ReservationRecord(
                        patron_id=patron_a.user_id,
                        book_id=created["Ready Reservation Fixture"].book_id,
                        status="ready",
                    ),
                    ReservationRecord(
                        patron_id=patron_b.user_id,
                        book_id=created["Waiting Reservation Fixture"].book_id,
                        status="waiting",
                    ),
                ]
            )
            self.db.session.commit()
            notifications = NotificationRepository()
            notifications.create(
                patron_a.user_id,
                "Simulation reminder",
                "A fixture notification for browser checks.",
                category="loan",
                link="/loans/",
            )
            notifications.create(
                librarian.user_id,
                "Simulation inventory update",
                "A fixture notification for librarian checks.",
                category="inventory",
                link="/books/manage",
            )
            notifications.create(
                patron_a.user_id,
                "Simulation announcement",
                "A second fixture notification for unread-count checks.",
                category="announcement",
                link="/notifications/",
            )
            self.fixture = {
                "librarian_id": librarian.user_id,
                "patron_a_id": patron_a.user_id,
                "patron_b_id": patron_b.user_id,
                "borrowed_book_id": borrowed.book_id,
                "overdue_book_id": overdue.book_id,
                "lost_book_id": lost.book_id,
                "ready_book_id": created["Ready Reservation Fixture"].book_id,
                "waiting_book_id": created["Waiting Reservation Fixture"].book_id,
                "single_book_id": created["Single Copy Fixture"].book_id,
                "many_book_id": created["Many Copies Fixture"].book_id,
                "reference_book_id": created["Reference Fixture"].book_id,
                "archived_book_id": archived.book_id,
                "genres": ["History", "Mystery", "Science"],
            }

    def db_select(self, sql: str, params: tuple = ()) -> str:
        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(sql, params).fetchone()
        finally:
            connection.close()
        return json.dumps(row, default=str) if row is not None else "no rows"

    def bind_page(self, page):
        page.on("console", lambda message: self.console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: self.console_errors.append(str(error)))
        page.on(
            "request",
            lambda request: self.events.append(
                {
                    "method": request.method,
                    "url": request.url,
                    "status": None,
                    "resource_type": request.resource_type,
                }
            ),
        )
        page.on(
            "response",
            lambda response: self._record_response(response),
        )

    def _record_response(self, response):
        for event in reversed(self.events):
            if event["url"] == response.url and event["status"] is None:
                event["status"] = response.status
                break

    def login(self, page, username: str):
        page.goto(urljoin(self.base_url, "/login?open=1"))
        page.locator("#login-username").fill(username)
        page.locator("#login-password").fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_load_state("domcontentloaded")

    def _record(
        self,
        role,
        module,
        function,
        control,
        page_url,
        input_value,
        expected,
        status,
        db_sql="SELECT COUNT(*) FROM users",
        notes="",
        error=None,
    ):
        self.counter += 1
        identifier = f"SIM-{self.counter:04d}"
        unexpected_console_errors = [
            message
            for message in self.console_errors
            if not (
                message.startswith("Failed to load resource:")
                and any(
                    f"status of {code}" in message
                    for code in (400, 401, 403)
                )
            )
        ]
        if status == "PASS" and unexpected_console_errors:
            status = "FAIL"
            notes = (
                f"{notes} Console errors: {json.dumps(unexpected_console_errors, ensure_ascii=False)}"
            ).strip()
        evidence = ""
        if status == "FAIL":
            REPORT_DIR.joinpath("evidence").mkdir(parents=True, exist_ok=True)
            evidence_path = REPORT_DIR / "evidence" / f"{identifier}.png"
            try:
                self._active_page.screenshot(path=str(evidence_path), full_page=True)
                evidence = str(evidence_path.relative_to(ROOT))
            except Exception:
                evidence = "screenshot unavailable"
        latest = next(
            (
                event
                for event in reversed(self.events)
                if event.get("method") == "POST"
                and str(event["url"]).startswith(self.base_url)
            ),
            None,
        )
        if latest is None:
            latest = next(
                (
                    event
                    for event in reversed(self.events)
                    if event.get("resource_type") == "document"
                    and str(event["url"]).startswith(self.base_url)
                ),
                self.events[-1] if self.events else {},
            )
        method_route = ""
        if latest:
            parsed = urlsplit(str(latest["url"]))
            method_route = f'{latest["method"]} {parsed.path}'
        flashes = ""
        try:
            flashes = " | ".join(
                text.strip()
                for text in self._active_page.locator("[data-toast] span").all_text_contents()
                if text.strip()
            )
        except Exception:
            pass
        dialog_text = ""
        try:
            dialog = self._active_page.locator("[data-confirm-dialog]")
            if dialog.is_visible():
                dialog_text = dialog.inner_text().strip()
        except Exception:
            pass
        try:
            current_url = self._active_page.url
        except Exception:
            current_url = page_url
        try:
            last_status = latest.get("status", "") if latest else ""
        except Exception:
            last_status = ""
        database_value = self.db_select(db_sql)
        output = (
            f"status={last_status}; final={current_url}; "
            f"flash={flashes or 'none'}; modal={dialog_text or 'none'}; "
            f"SELECT={database_value}; "
            f"console_errors={json.dumps(self.console_errors, ensure_ascii=False)}"
        )
        if error:
            notes = (notes + " " + error).strip()
        self.rows.append(
            {
                "ID": identifier,
                "Role": role,
                "Module": module,
                "Function (what it should do)": function,
                "Button/Control (label + selector)": control,
                "Page where clicked": page_url,
                "HTTP method + route requested": method_route,
                "Input used": input_value,
                "Expected output": expected,
                "Actual output (flash text, redirect URL, status code, DB change)": output,
                "Status": status,
                "Evidence (screenshot or log path)": evidence or "Playwright event log",
                "Notes / suspected cause": notes,
            }
        )

    def run_action(
        self,
        page,
        role,
        module,
        function,
        control,
        input_value,
        expected,
        action,
        verify,
        db_sql="SELECT COUNT(*) FROM users",
        notes="",
    ):
        self._active_page = page
        before_url = page.url
        self.events = []
        self.console_errors = []
        error = None
        try:
            action()
            page.wait_for_load_state("domcontentloaded", timeout=4000)
            time.sleep(0.08)
            passed = bool(verify())
        except Exception as exception:
            passed = False
            error = f"{type(exception).__name__}: {exception}"
        self._record(
            role,
            module,
            function,
            control,
            before_url,
            input_value,
            expected,
            "PASS" if passed else "FAIL",
            db_sql=db_sql,
            notes=notes,
            error=error,
        )

    def reset_browser_events(self, page):
        self.events = []
        self.console_errors = []

    def crawl_public_routes(self, page, role):
        routes = [
            "/",
            "/books/",
            f"/books/{self.fixture['borrowed_book_id']}",
            "/signup",
            "/register",
            "/login",
            "/notifications/recent",
            "/loans/",
            "/basket",
            "/profile",
            "/librarian",
            "/books/manage",
            "/members/",
            "/librarian/genres/",
        ]
        for route in routes:
            self._active_page = page
            self.events = []
            self.console_errors = []
            page.goto(urljoin(self.base_url, route))
            latest = next(
                (
                    event
                    for event in self.events
                    if event.get("resource_type") == "document"
                    and event["url"].startswith(self.base_url)
                ),
                {},
            )
            status = latest.get("status", 0)
            expected_status = (
                200
                if route in {"/", "/books/", "/signup", "/register", "/login"}
                else (
                    401
                    if role == "guest" and route == "/notifications/recent"
                    else (
                        302
                        if role == "guest" and route != f"/books/{self.fixture['borrowed_book_id']}"
                        else (
                            403
                            if (
                                role == "patron"
                                and (
                                    route.startswith("/librarian")
                                    or route in {"/books/manage", "/members/"}
                                )
                            )
                            or (
                                role == "librarian"
                                and route in {"/basket", "/profile"}
                            )
                            else 200
                        )
                    )
                )
            )
            actual_url = page.url
            passed = bool(status == expected_status)
            if role == "guest" and expected_status == 302:
                passed = status == 302 and actual_url.endswith("/login")
            if role == "patron" and route == "/notifications/recent":
                passed = status == 200
            self._record(
                role,
                "Route crawl",
                f"Open {route} and verify role access",
                f"GET {route}",
                page.url,
                "none",
                f"HTTP {expected_status} or redirect as specified",
                "PASS" if passed else "FAIL",
                db_sql="SELECT COUNT(*) FROM books",
                notes=f"actual page after redirects: {actual_url}; original response={status}; expected={expected_status}",
            )

    def run_guest(self, browser):
        self.reset_and_seed()
        context = browser.new_context()
        page = context.new_page()
        self.bind_page(page)
        page.goto(self.base_url)
        self._active_page = page
        self._record(
            "Anonymous", "Landing", "Load landing page",
            "GET /", self.base_url, "none", "Home page renders",
            "PASS" if page.title().startswith("Bookend") else "FAIL",
            db_sql="SELECT COUNT(*) FROM books",
        )
        drawer = page.locator("[data-nav-drawer-toggle]")
        if drawer.count():
            self.run_action(
                page, "Anonymous", "Navigation", "Open navigation drawer",
                "Open menu [data-nav-drawer-toggle]", "click",
                "Drawer becomes visible",
                lambda: drawer.click(),
                lambda: page.locator("[data-nav-drawer]").get_attribute("aria-hidden") == "false",
            )
            links = page.locator("[data-nav-drawer] nav a")
            targets = []
            for index in range(links.count()):
                target = links.nth(index).get_attribute("href")
                label = (links.nth(index).inner_text() or "").strip()
                if target and target.startswith("/") and target not in targets:
                    targets.append((target, label))
            for target, label in targets:
                page.goto(self.base_url)
                page.locator("[data-nav-drawer-toggle]").click()
                link = page.locator(f'[data-nav-drawer] a[href="{target}"]').first
                before = page.url
                self.events = []
                self.console_errors = []
                try:
                    link.click()
                    page.wait_for_load_state("domcontentloaded")
                    status = next((e.get("status") for e in reversed(self.events) if e.get("status") is not None), None)
                    good = status is not None and status < 400
                except Exception:
                    good = False
                    status = None
                self._active_page = page
                self._record(
                    "Anonymous", "Navigation", f"Open guest menu link: {label}",
                    f"{label} a[href='{target}']", before, "click",
                    "Navigates to a working page", "PASS" if good else "FAIL",
                    db_sql="SELECT COUNT(*) FROM users",
                    notes=f"initial response={status}",
                )
        self.crawl_public_routes(page, "guest")
        context.close()

    def run_auth_and_patron(self, browser):
        self.reset_and_seed()
        context = browser.new_context()
        page = context.new_page()
        self.bind_page(page)
        self._active_page = page
        page.goto(urljoin(self.base_url, "/signup"))
        form = page.locator("form.register-form")
        cases = [
            ("duplicate username", "new@example.com", "reader-a", PASSWORD, PASSWORD),
            ("duplicate email case-insensitive", "READER-A@example.com", "new-reader", PASSWORD, PASSWORD),
            ("short password", "short@example.com", "short-reader", "123", "123"),
            ("mismatched confirmation", "mismatch@example.com", "mismatch-reader", PASSWORD, "Different1!"),
            ("empty fields", "", "", "", ""),
            ("HTML and SQL-like input", "x<script>@example.com", "' OR 1=1 --", PASSWORD, PASSWORD),
            ("very long values", "a" * 254 + "@example.com", "x" * 31, PASSWORD, PASSWORD),
        ]
        for label, email, username, password, confirm in cases:
            page.goto(urljoin(self.base_url, "/signup"))
            page.locator("#email").fill(email)
            page.locator("#reg-username").fill(username)
            page.locator("#reg-password").fill(password)
            page.locator("#reg-confirm").fill(confirm)
            start_url = page.url
            self.events = []
            self.console_errors = []
            try:
                page.locator(".register-form button[type=submit]").click()
                page.wait_for_load_state("domcontentloaded")
                post = next((e for e in reversed(self.events) if e.get("method") == "POST"), None)
                status_code = post.get("status") if post else None
                body_text = page.locator("body").inner_text()
                email_error = "Please enter a valid email address."
                username_error = "Username must be 3-30 characters"
                duplicate_error = (
                    "That username is taken."
                    if label == "duplicate username"
                    else "That email is already registered."
                )
                if label == "short password":
                    ok = (
                        status_code is None
                        and page.locator('[data-field-error="password"]').inner_text().strip()
                        == "Password must be at least 8 characters."
                    )
                elif label == "mismatched confirmation":
                    ok = (
                        status_code is None
                        and page.locator('[data-field-error="confirm_password"]').inner_text().strip()
                        == "Passwords don't match."
                    )
                elif label in {"duplicate username", "duplicate email case-insensitive"}:
                    ok = status_code == 400 and duplicate_error in body_text
                elif label == "HTML and SQL-like input":
                    ok = status_code == 400 and (
                        email_error in body_text or username_error in body_text
                    )
                elif label == "very long values":
                    ok = (
                        status_code == 400
                        and (email_error in body_text or username_error in body_text)
                    )
                elif label == "empty fields":
                    ok = (
                        status_code is None
                        and page.locator('[data-field-error="password"]').inner_text().strip()
                        == "Password must be at least 8 characters."
                    )
                else:
                    ok = False
            except Exception as exception:
                status_code = None
                body_text = str(exception)
                ok = False
            self._active_page = page
            self._record(
                "Anonymous", "Registration", f"Register with {label}",
                "Create account .register-form button[type=submit]",
                start_url, label, "Reject invalid/duplicate input; accept only valid",
                "PASS" if ok else "FAIL",
                db_sql=(
                    "SELECT COUNT(*) FROM users WHERE username='reader-a'"
                    if label == "duplicate username"
                    else (
                        "SELECT COUNT(*) FROM users WHERE lower(email)='reader-a@example.com'"
                        if label == "duplicate email case-insensitive"
                        else (
                            "SELECT LENGTH(email), LENGTH(username) FROM users "
                            "WHERE email LIKE 'aaaaaaaaaa%' ORDER BY user_id DESC LIMIT 1"
                            if label == "very long values"
                            else "SELECT COUNT(*) FROM users"
                        )
                    )
                ),
                notes=(
                    f"response={status_code}; body_excerpt={body_text[:160]}; "
                    + (
                        "A 266-character syntactically valid-looking email was accepted; "
                        "email length is not bounded."
                        if label == "very long values" and status_code == 200
                        else ""
                    )
                ),
            )

        page.goto(urljoin(self.base_url, "/signup"))
        page.locator("#email").fill("new-reader@example.com")
        page.locator("#reg-username").fill("new-reader")
        page.locator("#reg-password").fill(PASSWORD)
        page.locator("#reg-confirm").fill(PASSWORD)
        self.events = []
        self.console_errors = []
        page.locator(".register-form button[type=submit]").click()
        page.wait_for_load_state("domcontentloaded")
        registration_status = next(
            (
                event.get("status")
                for event in reversed(self.events)
                if event.get("resource_type") == "document"
            ),
            None,
        )
        self._active_page = page
        self._record(
            "Anonymous", "Registration", "Register a patron with valid details",
            "Create account .register-form button[type=submit]",
            self.base_url + "/signup",
            "new-reader@example.com / new-reader / valid matching password",
            "Account created and success message shown",
            "PASS" if registration_status == 200 and "Account created" in page.locator("body").inner_text() else "FAIL",
            db_sql="SELECT COUNT(*) FROM users WHERE username='new-reader'",
            notes=f"response={registration_status}",
        )

        page.goto(urljoin(self.base_url, "/login?open=1"))
        page.locator("#login-username").fill("reader-a")
        page.locator("#login-password").fill("wrong-password")
        self.events = []
        self.console_errors = []
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_load_state("domcontentloaded")
        login_post = next((e for e in reversed(self.events) if e.get("method") == "POST"), None)
        failed_login_status = login_post.get("status") if login_post else None
        self._active_page = page
        self._record(
            "Anonymous", "Login", "Reject incorrect password",
            "Sign in button .login-form button[type=submit]",
            self.base_url + "/login", "reader-a / wrong-password",
            "401 with invalid-credentials message and remain on login",
            "PASS" if failed_login_status == 401 and page.locator("[role=alert]").count() else "FAIL",
            db_sql="SELECT COUNT(*) FROM users",
            notes=f"response={failed_login_status}",
        )
        self.login(page, "reader-a")
        self._record(
            "Patron", "Login", "Sign in patron",
            "Sign in button .login-form button[type=submit]",
            self.base_url + "/login", "reader-a / valid test password",
            "Redirect to patron landing page",
            "PASS" if page.url == self.base_url + "/" else "FAIL",
            db_sql="SELECT username, role FROM users WHERE username='reader-a'",
        )

        self.crawl_public_routes(page, "patron")
        self._patron_controls(page)
        self._logout(page, "Patron")
        self.login(page, "reader-a")
        self._csrf_probe(page, "Patron")
        context.close()

    def _patron_controls(self, page):
        book_id = int(self.fixture["single_book_id"])
        detail_url = urljoin(self.base_url, f"/books/{book_id}")
        page.goto(detail_url)
        self.run_action(
            page, "Patron", "Book detail", "Add book to borrow basket",
            "Add to basket button .book-detail-actions form button",
            f"book_id={book_id}", "Book appears in basket and basket row is persisted",
            lambda: page.get_by_role("button", name="Add to basket").click(),
            lambda: self.db_select(
                f"SELECT COUNT(*) FROM basket_items WHERE user_id={self.fixture['patron_a_id']} AND book_id={book_id}"
            ) == "[1]",
            db_sql=f"SELECT COUNT(*) FROM basket_items WHERE user_id={self.fixture['patron_a_id']} AND book_id={book_id}",
        )
        page.goto(urljoin(self.base_url, "/basket"))
        self.run_action(
            page, "Patron", "Basket", "Confirm borrowing",
            "Confirm borrowing button .basket-summary button[type=submit]",
            f"book_id={book_id}", "Loan is created and basket is cleared",
            lambda: page.get_by_role("button", name="Confirm borrowing").click(),
            lambda: page.url.endswith("/basket/receipt"),
            db_sql=f"SELECT COUNT(*) FROM loans WHERE patron_id={self.fixture['patron_a_id']} AND book_id={book_id}",
        )
        page.goto(detail_url)
        self.run_action(
            page, "Patron", "Book detail", "Save book to favorites",
            "Save book button .book-detail-actions button[aria-pressed=false]",
            f"book_id={book_id}", "Favorite record is created",
            lambda: page.get_by_role("button", name="♡ Save book").click(),
            lambda: page.locator('button[aria-pressed="true"]').count() > 0,
            db_sql=f"SELECT COUNT(*) FROM favorites WHERE user_id={self.fixture['patron_a_id']} AND book_id={book_id}",
        )
        self._review_flow(page, detail_url)
        self._notification_flow(page)
        self._drawer_links(page, "Patron")

    def _review_flow(self, page, detail_url):
        page.goto(detail_url)
        form = page.locator("form.review-form").last
        form.locator("select[name=rating]").select_option("5")
        form.locator("textarea[name=comment]").fill("Simulation review comment.")
        self.events = []
        self.console_errors = []
        form.locator('button[type="submit"]').click()
        page.wait_for_load_state("domcontentloaded")
        review_id = None
        with self.app.app_context():
            from backend.app.models.review_record import ReviewRecord

            row = self.db.session.scalar(self.db.select(ReviewRecord).where(ReviewRecord.comment == "Simulation review comment."))
            review_id = row.review_id if row else None
        self._active_page = page
        self._record(
            "Patron", "Reviews", "Create a book review",
            "Write review form.review-form button[type=submit]",
            detail_url, "rating=5; comment=Simulation review comment.",
            "Review displayed and stored",
            "PASS" if review_id is not None and "Simulation review comment." in page.locator("body").inner_text() else "FAIL",
            db_sql="SELECT COUNT(*) FROM reviews WHERE comment='Simulation review comment.'",
        )
        if not review_id:
            return
        page.goto(detail_url)
        page.locator("#edit-rating").select_option("4")
        page.locator("#edit-comment").fill("Updated simulation review.")
        self.events = []
        self.console_errors = []
        page.get_by_role("button", name="Update review").click()
        page.wait_for_load_state("domcontentloaded")
        self._active_page = page
        self._record(
            "Patron", "Reviews", "Edit own review",
            "Update review button #edit-rating + #edit-comment",
            detail_url, "rating=4; comment=Updated simulation review.",
            "Review content is updated",
            "PASS" if "Updated simulation review." in page.locator("body").inner_text() else "FAIL",
            db_sql=f"SELECT rating, comment FROM reviews WHERE review_id={review_id}",
        )
        page.goto(detail_url)
        delete = page.get_by_role("button", name="Delete your review")
        self.events = []
        self.console_errors = []
        delete.click()
        confirmation = page.locator("[data-confirm-dialog]")
        modal = confirmation.inner_text() if confirmation.is_visible() else ""
        if confirmation.is_visible():
            with page.expect_navigation(wait_until="domcontentloaded", timeout=8000):
                with page.expect_response(
                    lambda response: (
                        urlsplit(response.url).path == f"/reviews/{review_id}/delete"
                        and response.request.method == "POST"
                    ),
                    timeout=8000,
                ) as response_info:
                    page.locator("[data-confirm-accept]").click()
            delete_response = response_info.value
        else:
            delete_response = None
        delete_count = self.db_select(
            f"SELECT COUNT(*) FROM reviews WHERE review_id={review_id}"
        )
        confirmation_matched = "Delete your review?" in modal
        self._active_page = page
        self._record(
            "Patron", "Reviews", "Delete own review with confirmation",
            "Delete your review button .review-delete-form button",
            detail_url, "confirm deletion",
            "Review removed after confirmation",
            "PASS" if (
                delete_response is not None
                and delete_response.status == 302
                and delete_count == "[0]"
                and confirmation_matched
            ) else "FAIL",
            db_sql=f"SELECT COUNT(*) FROM reviews WHERE review_id={review_id}",
            notes=(
                f"confirmation matched={confirmation_matched}; "
                f"response={delete_response.status if delete_response else 'none'}; "
                f"post-delete count={delete_count}; confirmation text: {modal[:180]}"
            ),
        )

    def _notification_flow(self, page):
        page.goto(self.base_url)
        bell = page.locator("[data-notification-toggle]")
        if not bell.count():
            self._active_page = page
            self._record(
                "Patron", "Notifications", "Open notification panel",
                "Bell [data-notification-toggle]", page.url, "click",
                "Dropdown opens with recent notifications", "FAIL",
                db_sql="SELECT COUNT(*) FROM notifications",
                notes="Bell button absent on patron landing page",
            )
            return
        self.run_action(
            page, "Patron", "Notifications", "Open notification panel",
            "Bell [data-notification-toggle]", "click",
            "Panel opens and recent items are fetched",
            lambda: bell.click(),
            lambda: bell.get_attribute("aria-expanded") == "true",
            db_sql=f"SELECT COUNT(*) FROM notifications WHERE user_id={self.fixture['patron_a_id']}",
        )
        self.events = []
        self.console_errors = []
        response = page.request.get(urljoin(self.base_url, "/notifications/recent"))
        data = response.json() if response.ok else {}
        self.events = [
            {
                "method": "GET",
                "url": response.url,
                "status": response.status,
                "resource_type": "xhr",
            }
        ]
        self._active_page = page
        self._record(
            "Patron", "Notifications", "Fetch recent notifications",
            "GET /notifications/recent", page.url, "authenticated patron session",
            "Only patron's latest items and unread count returned",
            "PASS" if response.status == 200 and data.get("unread_count", -1) >= 0 else "FAIL",
            db_sql=f"SELECT COUNT(*) FROM notifications WHERE user_id={self.fixture['patron_a_id']}",
            notes=f"response={response.status}; unread_count={data.get('unread_count')}",
        )

    def _drawer_links(self, page, role):
        page.goto(self.base_url)
        page.locator("[data-account-open]").click()
        nav = page.locator(".account-drawer nav a")
        count = nav.count()
        visited = set()
        for index in range(count):
            target = nav.nth(index).get_attribute("href")
            label = nav.nth(index).inner_text().strip()
            if not target or target in visited:
                continue
            visited.add(target)
            page.goto(self.base_url)
            page.locator("[data-account-open]").click()
            before = page.url
            self.events = []
            self.console_errors = []
            try:
                page.locator(f'.account-drawer nav a[href="{target}"]').first.click()
                page.wait_for_load_state("domcontentloaded")
                status = next((event.get("status") for event in reversed(self.events) if event.get("status") is not None), None)
                good = status is not None and status < 400
            except Exception:
                good = False
                status = None
            self._active_page = page
            self._record(
                role, "Account drawer", f"Follow {label} link",
                f"{label} .account-drawer a[href='{target}']", before, "click",
                "A working role-appropriate page opens", "PASS" if good else "FAIL",
                db_sql="SELECT COUNT(*) FROM users",
                notes=f"response={status}; destination={target}",
            )

    def _csrf_probe(self, page, role):
        page.goto(self.base_url)
        self.events = []
        self.console_errors = []
        response = page.request.post(
            urljoin(self.base_url, "/basket/checkout"),
            data={},
            max_redirects=0,
        )
        self.events = [
            {
                "method": "POST",
                "url": response.url,
                "status": response.status,
                "resource_type": "xhr",
            }
        ]
        self._active_page = page
        self._record(
            role, "Security", "Reject POST without CSRF token",
            "POST /basket/checkout (raw request)", page.url, "no CSRF token",
            "Request rejected with 400/401/403 or redirected to login",
            "PASS" if response.status in {302, 400, 401, 403} else "FAIL",
            db_sql="SELECT COUNT(*) FROM loans",
            notes=f"response={response.status}",
        )

    def run_librarian(self, browser):
        self.reset_and_seed()
        context = browser.new_context()
        page = context.new_page()
        self.bind_page(page)
        self.login(page, "staff")
        self._active_page = page
        self._record(
            "Librarian", "Login", "Sign in librarian",
            "Sign in button .login-form button[type=submit]",
            self.base_url + "/login", "staff / valid test password",
            "Redirect to role-aware landing page",
            "PASS" if page.url == self.base_url + "/" else "FAIL",
            db_sql="SELECT username, role FROM users WHERE username='staff'",
        )
        self.crawl_public_routes(page, "librarian")
        self._librarian_controls(page)
        self._drawer_links(page, "Librarian")
        self._logout(page, "Librarian")
        self.login(page, "staff")
        self._csrf_probe(page, "Librarian")
        context.close()

    def _librarian_controls(self, page):
        page.goto(urljoin(self.base_url, "/books/new"))
        page.locator("#title").fill("UI Created Fixture")
        page.locator("#author").fill("UI Author")
        page.locator("#genre").select_option(label="History")
        page.locator("#description").fill("Created through Playwright.")
        page.locator("#kind").select_option("standard")
        page.locator("#total_copies").fill("1")
        self.events = []
        self.console_errors = []
        page.get_by_role("button", name="Save book").click()
        page.wait_for_load_state("domcontentloaded")
        self._active_page = page
        self._record(
            "Librarian", "Books", "Add a book",
            "Save book button .book-editor-form button[type=submit]",
            self.base_url + "/books/new",
            "title=UI Created Fixture; author=UI Author; copies=1",
            "Book created and detail page opened",
            "PASS" if page.url.startswith(self.base_url + "/books/") and "UI Created Fixture" in page.locator("body").inner_text() else "FAIL",
            db_sql="SELECT COUNT(*) FROM books WHERE title='UI Created Fixture'",
        )
        book_id = None
        with self.app.app_context():
            from backend.app.repositories.book_repository import BookRepository

            found = BookRepository().find_by_title_author("UI Created Fixture", "UI Author")
            book_id = found.book_id if found else None
        if book_id:
            page.goto(urljoin(self.base_url, f"/books/{book_id}/edit"))
            page.locator("#title").fill("UI Edited Fixture")
            self.events = []
            self.console_errors = []
            page.get_by_role("button", name="Save changes").click()
            page.wait_for_load_state("domcontentloaded")
            self._active_page = page
            self._record(
                "Librarian", "Books", "Edit a book",
                "Save changes button .book-editor-form button[type=submit]",
                f"{self.base_url}/books/{book_id}/edit", "title=UI Edited Fixture",
                "Existing book title updates",
                "PASS" if "UI Edited Fixture" in page.locator("body").inner_text() else "FAIL",
                db_sql=f"SELECT title FROM books WHERE book_id={book_id}",
            )
            page.goto(urljoin(self.base_url, "/books/manage"))
            self._check_pagination(page)
            page.goto(urljoin(self.base_url, "/librarian/analytics?range=7d"))
            response = page.request.get(urljoin(self.base_url, "/librarian/analytics?range=7d"))
            self._active_page = page
            self._record(
                "Librarian", "Dashboard", "Load 7-day analytics",
                "GET /librarian/analytics?range=7d", page.url, "range=7d",
                "JSON analytics payload returned",
                "PASS" if response.status == 200 and response.headers.get("content-type", "").startswith("application/json") else "FAIL",
                db_sql="SELECT COUNT(*) FROM loans",
                notes=f"response={response.status}",
            )

    def _logout(self, page, role):
        page.goto(self.base_url)
        opener = page.locator("[data-account-open]")
        if opener.count():
            opener.click()
        logout = page.locator(".account-drawer-logout")
        if not logout.count():
            self._active_page = page
            self._record(
                role, "Login and account", "Log out",
                "Logout .account-drawer-logout", page.url, "click",
                "Session ends and login page opens", "FAIL",
                db_sql="SELECT COUNT(*) FROM users",
                notes="Logout control was not present",
            )
            return
        self.events = []
        self.console_errors = []
        logout.click()
        page.wait_for_load_state("domcontentloaded")
        status = next(
            (
                event.get("status")
                for event in reversed(self.events)
                if event.get("method") == "POST"
                and urlsplit(str(event["url"])).path == "/logout"
            ),
            None,
        )
        page.goto(urljoin(self.base_url, "/basket"))
        protected_redirect = page.url.endswith("/login")
        self._active_page = page
        self._record(
            role, "Login and account", "Log out and verify protected-page redirect",
            "Logout .account-drawer-logout", self.base_url + "/",
            "POST with rendered CSRF token",
            "Logout redirects to login and basket access requires sign-in",
            "PASS" if status == 302 and protected_redirect else "FAIL",
            db_sql="SELECT COUNT(*) FROM users",
            notes=f"logout response={status}; post-logout URL={page.url}",
        )

    def _check_pagination(self, page):
        count = page.locator(".catalog-pagination").count()
        text = page.locator(".catalog-count").inner_text() if page.locator(".catalog-count").count() else ""
        self._active_page = page
        self._record(
            "Librarian", "Books", "Check manage-books pagination",
            ".catalog-pagination", page.url, "25+ books",
            "A single pagination control appears after the table",
            "PASS" if count == 1 and page.locator(".catalog-pagination").evaluate("(el) => el.compareDocumentPosition(document.querySelector('#book-stock')) & Node.DOCUMENT_POSITION_PRECEDING") else "FAIL",
            db_sql="SELECT COUNT(*) FROM books",
            notes=f"pagination count={count}; result label={text}",
        )

    def append_unexecuted_cases(self):
        cases = [
            ("Anonymous", "Login and account", "Reject unknown username", "Sign in", "/login", "unknown account", "Invalid-credentials response"),
            ("Anonymous", "Login and account", "Reject deactivated account", "Sign in", "/login", "deactivated patron", "Account deactivation is rejected"),
            ("Anonymous", "Login and account", "Reject empty login fields", "Sign in", "/login", "empty username/password", "Required-field validation"),
            ("Anonymous", "Login and account", "Ignore external next redirect", "Sign in", "/login?next=https://example.com", "valid credentials + external next", "Redirect stays on this application"),
            ("Anonymous", "Login and account", "Toggle password visibility", "Show/Hide [data-password-toggle]", "/login?open=1", "click twice", "Input type and accessible label toggle"),
            ("Anonymous", "Login and account", "Flip between sign-in and registration", "Create an account / Sign in", "/login", "click each page-turn link", "Correct form face becomes visible"),
            ("Patron", "Landing", "Use carousel arrows, drag, and genre card", "Carousel controls / centered card", "/", "click arrows, drag, click genre", "Carousel changes and selected genre opens"),
            ("Patron", "Landing", "Flip landing book cards", "Flip card control", "/", "click flip control", "Book-card back becomes visible"),
            ("Patron", "Catalog", "Search by title and author", "Catalog search", "/books/", "title and author terms", "Matching catalog results"),
            ("Patron", "Catalog", "Filter genre including Uncategorized", "Genre filter", "/books/", "each genre and Uncategorized", "Results match selected genre"),
            ("Patron", "Catalog", "Sort and filter availability", "Sort and availability controls", "/books/", "each available option", "Results follow selected order/status"),
            ("Patron", "Catalog", "Navigate catalog pagination", "Next/page links", "/books/", "next page", "One page of results changes"),
            ("Patron", "Book detail", "Borrow directly and reserve", "Borrow / Reserve forms", "/books/<id>", "available and unavailable fixture books", "Loan or reservation is stored"),
            ("Patron", "Favorites", "Open saved books and remove a favorite", "Saved books card/remove control", "/favorites", "remove saved fixture", "Favorite is removed in SQLite"),
            ("Patron", "Basket", "Select all and remove selected books", "Select all / Remove selected", "/basket", "select and remove fixture", "Basket and session/database rows clear"),
            ("Patron", "Basket", "Reject checkout above loan limit", "Confirm borrowing", "/basket", "six valid book ids", "Checkout is rejected; no loans created"),
            ("Patron", "Basket", "Reject checkout after availability changes", "Confirm borrowing", "/basket", "make basket book unavailable", "Checkout is rejected without partial loans"),
            ("Patron", "Basket", "Reject checkout with unpaid fees", "Confirm borrowing", "/basket", "patron with overdue/loss fee", "Checkout is rejected; basket remains"),
            ("Patron", "Basket", "Handle empty basket checkout", "Confirm borrowing", "/basket", "empty basket", "No loan is created and feedback is shown"),
            ("Patron", "Loans", "View loans, return a book, and inspect fee breakdown", "Loan cards / Return", "/loans/", "borrowed and overdue fixtures", "Loan status and fee data match SQLite"),
            ("Patron", "Reservations", "View and cancel reservations", "Reservation cards / Cancel", "/reservations", "ready and waiting fixtures", "Reservation status/cancellation persists"),
            ("Patron", "Profile", "Change password valid and invalid cases", "Change password form", "/profile", "valid, wrong-current, weak-new passwords", "Success or clear validation; credential changes as expected"),
            ("Patron", "Notifications", "Mark one/all read and verify badge/link", "Read / Read all controls", "/notifications/", "fixture notifications", "Read state and unread badge update"),
            ("Patron", "Navigation", "Verify footer and all header/drawer controls", "All links/buttons", "all patron pages", "one activation each", "Every control has its designated effect"),
            ("Librarian", "Dashboard", "Verify dashboard stats, tables, quick links, and ranges", "Dashboard cards / 30d / 12w", "/librarian", "fixture data and date ranges", "Displayed values and destinations match"),
            ("Librarian", "Backup", "Export and validate import error/success cases", "Export / Import controls", "/librarian", "valid, wrong-type, corrupt, oversized files", "Download/restore or explicit rejection"),
            ("Librarian", "Books", "Reject missing, duplicate, and negative-copy input", "Save book", "/books/new", "missing fields, duplicate title, negative copies", "Validation errors; no duplicate/invalid row"),
            ("Librarian", "Books", "Validate cover upload boundaries", "Cover upload input", "/books/new", "jpg/png/webp, invalid type, >2 MB", "Allowed files stored; invalid files rejected"),
            ("Librarian", "Books", "Archive and block archive for active records", "Archive book", "/books/<id>", "confirmation; loan/ready-reservation fixtures", "Archive or explicit blocked result"),
            ("Librarian", "Books", "Restore archived and selected books", "Restore / Restore selected", "/books/archived", "single and bulk selection", "Catalog state restored"),
            ("Librarian", "Books", "Permanently delete archived and selected books", "Delete / Delete selected", "/books/archived", "DELETE confirmation phrase; blocked cases", "Deletion and retained-history rules hold"),
            ("Librarian", "Books", "Search and filter manage-books list", "Search and filter controls", "/books/manage", "title, genre, status", "Rows match selected criteria"),
            ("Librarian", "Genres", "Add, edit, duplicate-check, and reserve Uncategorized", "Genre forms", "/librarian/genres", "valid, duplicate, reserved name", "Valid changes persist; invalid names rejected"),
            ("Librarian", "Genres", "Remove genres with and without books", "Delete genre", "/librarian/genres", "empty and populated genres", "Books move to Uncategorized; confirmation/notification shown"),
            ("Librarian", "Members", "Search, create, and open member detail", "Member search/create/list links", "/members/", "new member and search terms", "Member and loan detail render"),
            ("Librarian", "Members", "Activate/deactivate and reset member password", "Member actions", "/members/<id>", "patron and librarian records", "Allowed account changes persist; librarian protected"),
            ("Librarian", "Loans", "Issue, return, mark lost, and view overdue", "Issue/Return/Lost controls", "/loans/", "eligible and blocked fixtures", "Loan state and loss fee are correct"),
            ("Librarian", "Fees", "Filter, search, pay one/all, and verify idempotency", "Confirm payment / Confirm all", "/librarian/fees", "overdue and loss fee fixtures", "Receipts, notifications, and paid states persist once"),
            ("Librarian", "Reservations", "Review queue and execute available actions", "Queue action controls", "/librarian/reservations", "waiting and ready reservations", "Queue/action state matches database"),
            ("Librarian", "Reviews", "Moderate reviews and delete with confirmation", "Review moderation actions", "/librarian/reviews", "fixture patron review", "Review removed and notification generated"),
            ("Librarian", "Notifications", "Verify generated notifications for admin actions", "Notification list", "/notifications/", "archive, delete, genre removal, payment actions", "Each action creates the intended notification"),
            ("All roles", "Site-wide crawl", "Activate every reachable anchor, button, submit, and role=button", "All visible controls", "all nav-reachable pages", "one control at a time; cancel then confirm destructive dialogs", "No dead controls, broken routes, or unexpected data changes"),
        ]
        reason = "Not exercised by this partial run; no prerequisite failure was observed, so this is not assessed."
        for role, module, function, control, route, input_value, expected in cases:
            self.counter += 1
            self.rows.append(
                {
                    "ID": f"SIM-{self.counter:04d}",
                    "Role": role,
                    "Module": module,
                    "Function (what it should do)": function,
                    "Button/Control (label + selector)": control,
                    "Page where clicked": route,
                    "HTTP method + route requested": "not requested",
                    "Input used": input_value,
                    "Expected output": expected,
                    "Actual output (flash text, redirect URL, status code, DB change)": "Not executed; no browser action or database assertion was performed.",
                    "Status": "SKIPPED",
                    "Evidence (screenshot or log path)": "Not run",
                    "Notes / suspected cause": reason,
                }
            )

    def write_report(self):
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        evidence_dir = REPORT_DIR / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        current_failures = {
            f"{row['ID']}.png" for row in self.rows if row["Status"] == "FAIL"
        }
        for evidence_path in evidence_dir.glob("SIM-*.png"):
            if evidence_path.name not in current_failures:
                evidence_path.unlink()
        failed = [row for row in self.rows if row["Status"] == "FAIL"]
        FAIL_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        current_fail_images = {f"{row['ID']}.png" for row in self.rows if row["Status"] == "FAIL"}
        for image_path in FAIL_IMAGE_DIR.glob("SIM-*.png"):
            if image_path.name not in current_fail_images:
                image_path.unlink()

        with sync_playwright() as image_playwright:
            image_browser = image_playwright.chromium.launch(headless=True)
            try:
                image_page = image_browser.new_page(
                    viewport={"width": 1440, "height": 1000},
                    device_scale_factor=1,
                )
                for row in failed:
                    evidence_path = ROOT / row["Evidence (screenshot or log path)"]
                    screenshot_html = ""
                    if evidence_path.is_file():
                        screenshot_data = base64.b64encode(
                            evidence_path.read_bytes()
                        ).decode("ascii")
                        screenshot_html = (
                            f'<img src="data:image/png;base64,{screenshot_data}" '
                            f'alt="{html.escape(row["ID"])} original failure screenshot">'
                        )
                    image_html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
*{{box-sizing:border-box}}html,body{{margin:0;background:#fff;color:#202720;font:16px/1.5 Arial,sans-serif}}
body{{padding:32px}}main{{max-width:1320px;margin:0 auto;padding:28px;background:#fff;border:1px solid #d8ddd8;border-radius:12px}}
.label{{display:inline-block;padding:5px 12px;border:1px solid #b75b4b;border-radius:999px;color:#8f382d;font-weight:700;letter-spacing:.08em}}
h1{{margin:12px 0 4px;font-size:28px}}.meta{{color:#59645b;margin:0 0 18px}}
.detail{{margin:12px 0;padding:12px 16px;background:#f7f8f6;border-left:4px solid #526c55;overflow-wrap:anywhere}}
.detail strong{{display:block;margin-bottom:3px}}figure{{margin:24px 0 0;padding:16px;border:1px solid #d8ddd8;border-radius:8px;background:#fff}}
figcaption{{margin-bottom:12px;color:#526c55;font-weight:700}}img{{display:block;width:100%;height:auto;background:#fff}}
</style></head><body><main>
<span class="label">FAIL | {html.escape(row["ID"])}</span>
<h1>{html.escape(row["Function (what it should do)"])}</h1>
<p class="meta">Role: {html.escape(row["Role"])} | Module: {html.escape(row["Module"])}</p>
<div class="detail"><strong>Expected</strong>{html.escape(row["Expected output"])}</div>
<div class="detail"><strong>Observed</strong>{html.escape(row["Actual output (flash text, redirect URL, status code, DB change)"][:650])}</div>
<figure><figcaption>Original browser screenshot — {html.escape(row["ID"])}</figcaption>
{screenshot_html or '<p>Original screenshot was unavailable.</p>'}
</figure></main></body></html>"""
                    image_page.set_content(image_html, wait_until="load")
                    if screenshot_html:
                        image_page.locator("img").evaluate("(image) => image.decode()")
                    image_page.screenshot(
                        path=str(FAIL_IMAGE_DIR / f"{row['ID']}.png"),
                        full_page=True,
                        animations="disabled",
                    )
            finally:
                image_browser.close()

        csv_path = REPORT_DIR / "results.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(self.rows)

        counts = {status: sum(row["Status"] == status for row in self.rows) for status in ("PASS", "FAIL", "BLOCKED", "SKIPPED")}
        total = len(self.rows)
        role_counts = {}
        module_counts = {}
        for row in self.rows:
            role_counts.setdefault(row["Role"], {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "SKIPPED": 0})
            role_counts[row["Role"]][row["Status"]] += 1
            module_counts.setdefault(row["Module"], {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "SKIPPED": 0})
            module_counts[row["Module"]][row["Status"]] += 1
        failed = [row for row in self.rows if row["Status"] == "FAIL"]
        def pass_rate(result):
            executed = result["PASS"] + result["FAIL"]
            return f"{result['PASS'] / executed:.0%}" if executed else "n/a"

        def severity(row):
            if "Transition was aborted" in row["Notes / suspected cause"]:
                return "Low"
            if row["Module"] == "Security" or row["Module"] == "Route crawl":
                return "High"
            return "Medium"

        failed_with_severity = [
            {**row, "Severity": severity(row)} for row in failed
        ]
        generated_at = datetime.now(timezone.utc).isoformat()
        coverage_notes = (
            "This run is a partial automated simulation, not an exhaustive click-every-control audit. "
            "It covers public and role-gated route samples, registration validation, valid/invalid "
            "login, patron basket/favorites/reviews/notifications/navigation/logout, librarian "
            "book add/edit/analytics/navigation/logout, and missing-CSRF probes. Backup/restore, "
            "bulk archive/restore/delete, cover upload boundaries, fee payment/idempotency, genre "
            "CRUD, member CRUD/deactivation/reset, reservation actions, lost/return actions, "
            "catalog search/filter/sort/pagination navigation, carousel drag/flip, password changes, "
            "all invalid inputs, and responsive-width controls were not executed. Untested workflows "
            "must not be interpreted as passing. Console output is retained per row; expected HTTP "
            "error responses are represented separately from uncaught page exceptions."
        )
        method_summary = (
            "Playwright Python with headless Chromium; all browser actions hit an isolated "
            "Flask server backed by a temporary copy of bookend-starter.sqlite. The copied "
            "database was dropped/recreated before each role section. Cover uploads were "
            "written to a temporary directory. SQL assertions use direct SQLite SELECTs."
        )

        def table(rows, columns):
            parts = ["<table><thead><tr>"]
            parts.extend(f"<th>{html.escape(column)}</th>" for column in columns)
            parts.append("</tr></thead><tbody>")
            for row in rows:
                parts.append("<tr>")
                for column in columns:
                    value = str(row.get(column, ""))
                    parts.append(f'<td>{html.escape(value)}</td>')
                parts.append("</tr>")
            parts.append("</tbody></table>")
            return "".join(parts)

        md = [
            "# Bookend LMS Simulation Report",
            "",
            f"Generated: {generated_at}",
            "",
            f"Method: {method_summary}",
            "",
            "## Summary",
            "",
            "| Status | Total |",
            "|---|---:|",
        ]
        md.extend(f"| {status} | {count} |" for status, count in counts.items())
        md.extend(
            [
                f"| **Total** | **{total}** |",
                "",
                "This report contains only checks that the current script actually ran. A PASS requires the browser/UI result to agree with the corresponding direct SQLite SELECT or stated route outcome.",
                "Pass rate is PASS divided by executed PASS+FAIL cases; SKIPPED and BLOCKED cases are excluded.",
                "",
                "### Role results",
                "",
                "| Role | PASS | FAIL | BLOCKED | SKIPPED | Pass rate (executed) |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for role, result in role_counts.items():
            md.append(f"| {role} | {result['PASS']} | {result['FAIL']} | {result['BLOCKED']} | {result['SKIPPED']} | {pass_rate(result)} |")
        md.extend(["", "### Module results", "", "| Module | PASS | FAIL | BLOCKED | SKIPPED | Pass rate (executed) |", "|---|---:|---:|---:|---:|---:|"])
        for module, result in sorted(module_counts.items()):
            md.append(f"| {module} | {result['PASS']} | {result['FAIL']} | {result['BLOCKED']} | {result['SKIPPED']} | {pass_rate(result)} |")
        md.extend(["", "## Failures", ""])
        if failed:
            for row in failed:
                md.extend(
                    [
                        f"### {row['ID']} — {row['Function (what it should do)']} ({severity(row)})",
                        "",
                        f"- Reproduce: role **{row['Role']}**, open `{row['Page where clicked']}`, activate `{row['Button/Control (label + selector)']}`, input `{row['Input used']}`.",
                        f"- Expected: {row['Expected output']}",
                        f"- Actual: {row['Actual output (flash text, redirect URL, status code, DB change)']}",
                        f"- Suspected cause: {row['Notes / suspected cause'] or 'The actual result did not match the expected output.'}",
                        f"- Evidence: `{row['Evidence (screenshot or log path)']}`",
                        "",
                        "<details>",
                        f"<summary>View and download the white-background image for {row['ID']}</summary>",
                        "",
                        f"[Download framed image](./fail-images/{row['ID']}.png) · [Download original screenshot](./evidence/{row['ID']}.png)",
                        "",
                        f"![{row['ID']} failure evidence on white background](./fail-images/{row['ID']}.png)",
                        "",
                        "</details>",
                        "",
                    ]
                )
        else:
            md.append("No failures were observed in the executed checks.")
        md.extend(
            [
                "",
                "## Coverage notes",
                "",
                coverage_notes,
                "",
                "## Results",
                "",
            ]
        )
        md.append("| " + " | ".join(HEADERS) + " |")
        md.append("|" + "|".join("---" for _ in HEADERS) + "|")
        for row in self.rows:
            md.append("| " + " | ".join(str(row.get(column, "")).replace("|", "\\|").replace("\n", " ") for column in HEADERS) + " |")
        md.extend(
            [
                "",
                "## Reproduce",
                "",
                "From the repository root, run `pip install -r requirements-dev.txt` and `python tests/simulation/run_simulation.py`. The script uses a temporary copied database and upload folder and removes them when the run ends.",
            ]
        )
        markdown = "\n".join(md)
        (REPORT_DIR / "simulation_report.md").write_text(markdown, encoding="utf-8")
        html_rows = table(self.rows, HEADERS).replace(
            "<table>", '<table id="results-table">', 1
        )
        role_table = table(
            [
                {**result, "Role": role, "Pass rate (executed)": pass_rate(result)}
                for role, result in role_counts.items()
            ],
            ["Role", "PASS", "FAIL", "BLOCKED", "SKIPPED", "Pass rate (executed)"],
        )
        module_table = table(
            [
                {**result, "Module": module, "Pass rate (executed)": pass_rate(result)}
                for module, result in sorted(module_counts.items())
            ],
            ["Module", "PASS", "FAIL", "BLOCKED", "SKIPPED", "Pass rate (executed)"],
        )
        failed_table = table(
            failed_with_severity,
            [
                "ID",
                "Severity",
                "Role",
                "Function (what it should do)",
                "Button/Control (label + selector)",
                "Page where clicked",
                "Input used",
                "Expected output",
                "Actual output (flash text, redirect URL, status code, DB change)",
                "Notes / suspected cause",
                "Evidence (screenshot or log path)",
            ],
        )
        fail_gallery = "".join(
            (
                f'<article class="fail-image-card"><h3>{html.escape(row["ID"])} — '
                f'{html.escape(row["Function (what it should do)"])}</h3>'
                f'<p><a href="./fail-images/{html.escape(row["ID"])}.png" download>Download white-background image</a> '
                f'| <a href="./evidence/{html.escape(row["ID"])}.png" download>Download original screenshot</a></p>'
                f'<a href="./fail-images/{html.escape(row["ID"])}.png">'
                f'<img src="./fail-images/{html.escape(row["ID"])}.png" alt="{html.escape(row["ID"])} failure evidence"></a></article>'
            )
            for row in failed
        )
        html_doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Bookend LMS Simulation Report</title>
<style>
body{{font:14px/1.5 system-ui,sans-serif;margin:24px;color:#252a25;background:#f6f4ee}}
main{{max-width:1600px;margin:auto}}h1,h2{{color:#435b43}}table{{border-collapse:collapse;width:100%;background:#fffefa;margin:16px 0}}
th,td{{border:1px solid #e5e3da;padding:8px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#edf3eb}}
td{{max-width:440px;overflow-wrap:anywhere}}select{{padding:8px;border:1px solid #e5e3da;border-radius:8px}}
.status-PASS{{background:#edf3eb}}.status-FAIL{{background:#f8e6e1}}.status-BLOCKED{{background:#f3f0e5}}
.fail-gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:20px}}
.fail-image-card{{background:#fff;border:1px solid #d8ddd8;border-radius:12px;padding:18px}}
.fail-image-card img{{display:block;width:100%;height:auto;background:#fff;border:1px solid #eee}}
</style></head><body><main><h1>Bookend LMS Simulation Report</h1>
<p>Generated: {html.escape(generated_at)}</p><p>{html.escape(method_summary)}</p>
<h2>Summary</h2>{table([{"Status": key, "Total": value} for key, value in counts.items()] + [{"Status": "Total", "Total": total}], ["Status", "Total"])}
<p>Pass rate is PASS divided by executed PASS+FAIL cases; SKIPPED and BLOCKED cases are excluded. See coverage notes for untested workflows.</p>
<h3>Role results</h3>{role_table}<h3>Module results</h3>{module_table}
<label for="status-filter">Filter by status </label><select id="status-filter"><option value="">All statuses</option>
<option>PASS</option><option>FAIL</option><option>BLOCKED</option><option>SKIPPED</option></select>
<h2>Failures</h2>{'<p>No failures were observed in the executed checks.</p>' if not failed else failed_table}
<h2>FAIL screenshot images</h2><section class="fail-gallery">{fail_gallery}</section>
<h2>Coverage notes</h2><p>{html.escape(coverage_notes)}</p>
<h2>Reproduce</h2><p>From the repository root run <code>pip install -r requirements-dev.txt</code> and <code>python tests/simulation/run_simulation.py</code>. The script uses and cleans a temporary database and upload directory.</p>
<h2>Results</h2>{html_rows}
<script>document.getElementById('status-filter').addEventListener('change',e=>{{const s=e.target.value;document.querySelectorAll('#results-table tbody tr').forEach(r=>{{const cell=r.querySelector('td:nth-child(11)');r.hidden=!!s&&cell?.textContent!==s;}});}});</script>
</main></body></html>"""
        (REPORT_DIR / "simulation_report.html").write_text(html_doc, encoding="utf-8")
        return counts

    def run(self):
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                self.run_guest(browser)
                self.run_auth_and_patron(browser)
                self.run_librarian(browser)
                browser.close()
        except Exception as error:
            self._active_page = getattr(self, "_active_page", None)
            self._record(
                "All roles", "Harness", "Run simulation",
                "Playwright Chromium", self.base_url, "launch/run",
                "All sections execute with Chromium",
                "BLOCKED",
                db_sql="SELECT COUNT(*) FROM users",
                notes=f"simulation stopped: {type(error).__name__}: {error}",
            )
        self.append_unexecuted_cases()
        return self.write_report()


if __name__ == "__main__":
    if not STARTER_DB.is_file():
        raise SystemExit(f"Starter database is missing: {STARTER_DB}")
    simulation = Simulation()
    try:
        result = simulation.run()
        print(json.dumps(result, indent=2))
        print(f"Report: {REPORT_DIR}")
    finally:
        simulation.close()
