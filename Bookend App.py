import os
import string
from datetime import date
from functools import wraps
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bookend.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

STAFF_CODE = os.environ.get("STAFF_CODE")

# ── Models ────────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"

    user_id       = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20),  nullable=False, default="patron")
    active        = db.Column(db.Boolean,     nullable=False, default=True)

    loans = db.relationship("Loan", backref="patron", lazy=True)

    PERMISSIONS = {
        "patron":    {"search_book", "view_book", "borrow_book", "return_book",
                      "view_payments", "pay_late_fee", "pay_loss"},
        "librarian": {"search_book", "view_book", "add_book", "edit_book",
                      "archive_book", "update_return_status", "manage_mem"},
    }

    def check_pass(self, password):
        return check_password_hash(self.password_hash, password)

    def has_perm(self, perm):                       # fixed: was comparing dict to itself
        return perm in self.PERMISSIONS.get(self.role, set())

    def is_patron(self):
        return self.role == "patron"

    def is_librarian(self):
        return self.role == "librarian"


class Book(db.Model):
    __tablename__ = "books"

    book_id     = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False)
    author      = db.Column(db.String(120), nullable=False)
    genre       = db.Column(db.String(80))
    description = db.Column(db.Text)
    available   = db.Column(db.Boolean, nullable=False, default=True)
    catalog     = db.Column(db.Boolean, nullable=False, default=True)

    loans = db.relationship("Loan", backref="book", lazy=True)

    def matches_search(self, term):
        t = term.lower()
        return t in self.title.lower() or t in self.author.lower()

    def borrow(self):
        if not self.available:
            return False, "This book is currently borrowed"
        self.available = False
        return True, "Book marked as borrowed"

    def return_book(self):
        if self.available:
            return False, "This book is already available"
        self.available = True
        return True, "Book has been returned and is now available"


class Loan(db.Model):
    __tablename__ = "loans"

    loan_id     = db.Column(db.Integer, primary_key=True)
    patron_id   = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    book_id     = db.Column(db.Integer, db.ForeignKey("books.book_id"), nullable=False)
    borrowed_at = db.Column(db.Date, nullable=False, default=date.today)
    due_date    = db.Column(db.Date, nullable=False)
    returned_at = db.Column(db.Date)
    late_fee    = db.Column(db.Float, nullable=False, default=0.0)

    def is_returned(self):
        return self.returned_at is not None

    def is_overdue(self, current_date=None):
        current_date = current_date or date.today()
        end = self.returned_at if self.is_returned() else current_date
        return end > self.due_date

    def calculate_late_fee(self, daily_fee, current_date=None):
        current_date = current_date or date.today()
        if not self.is_overdue(current_date):
            self.late_fee = 0.0
            return 0.0
        end = self.returned_at or current_date
        self.late_fee = (end - self.due_date).days * daily_fee
        return self.late_fee

    def mark_returned(self, returned_at=None):
        if self.is_returned():
            return
        self.returned_at = returned_at or date.today()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _pass_strength(password):
    checks = [
        any(c in string.ascii_uppercase for c in password),
        any(c in string.ascii_lowercase for c in password),
        any(c in string.punctuation     for c in password),
        any(c in string.digits          for c in password),
    ]
    length = len(password)
    score = sum(1 for n in (8, 10, 12, 14) if length >= n)
    score += sum(1 for t in (1, 2, 3) if sum(checks) > t)
    return score                                    # fixed: was missing return


def pass_feedback(password):
    score = _pass_strength(password)
    if score < 4:
        msg = "Weak — add uppercase, lowercase, digits, and special characters."
    elif score == 4:
        msg = "Sufficient — consider making it longer."
    elif score < 7:
        msg = "Moderately strong — still has room for improvement."
    else:
        msg = "Strong password!"
    return score, msg


class AuthService:
    @staticmethod
    def register(email, username, password, confirm_pass, provided_code=""):
        email    = email.strip()
        username = username.strip()

        if not email or not username or not password:
            return False, "All fields are required."

        if password != confirm_pass:
            return False, "Passwords do not match."

        score, msg = pass_feedback(password)
        if score < 4:
            return False, msg

        # fixed: was comparing staff_code to itself (always False)
        role = "librarian" if (provided_code and provided_code == STAFF_CODE) else "patron"
        if provided_code and role != "librarian":
            return False, "Incorrect staff code."

        if User.query.filter_by(email=email).first():
            return False, "Email already exists."

        if User.query.filter_by(username=username).first():
            return False, "Username already taken."

        user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        return True, "Account created successfully."

    @staticmethod
    def login(username, password):
        user = User.query.filter_by(username=username).first()
        if user and user.active and user.check_pass(password):
            return user
        return None


# ── DB init ───────────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
