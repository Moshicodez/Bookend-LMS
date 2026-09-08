import os
import string
import sqlite3

            # For due dates, loans and late fee settlement in real time
from datetime import date, timedelta

            # For login/registration section (password hashing for security)
from werkzeug.security import (generate_password_hash, check_password_hash)

            # Flask integration
from flask import (Flask, render_template, request, redirect, url_for, flash, session)

from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key'

            # Source of Bookend data (users, books, loans, registered information)
database = "bookend.db"

            # Required code for librarian in login/registration to access 
            # librarian exclusive permissions and privileges
staff_code = "B0ok3nd Nvr Ends!"

def db_connect():
    # initial database connection
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row

            # Disclaimer: All code logic and conditions are subject to change
            #             once system is subject to testing 

            # General permissions and actions applied to both patron(reader)/librarian(staff)
class User:
    def __init__ (self, user_id, email, username, password_hash, role, active = True):
        self.user_id = user_id
        self.email = email
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.active = active

    def check_pass(self, password):
        return check_password_hash (self.password_hash, password)

    def perms(self, permission):
        permission = {"patron" :{"search_book", "view_book", "borrow_book", "return_book", 
                                 "view_payments", "pay_late_fee", "pay_loss"},
                    "librarian":{"search_book", "view_book", "add_book", "edit_book", "archive_book", 
                                 "update_return_status", "manage_mem"}}
        return permission in permission.get(self.role, set())

    def is_patron(self):
        return self.role == "patron"

    def is_librarian(self):
        return self.role == "librarian"



            # Authentication, login, and password verification and strength
class AuthService:
    @staticmethod
    def pass_strength(password_hash):
        UpperC = any([1 if c in string.ascii_uppercase else 0 for c in password_hash])
        LowerC = any([1 if c in string.ascii_lowercase else 0 for c in password_hash])
        SpecialC = any([1 if c in string.punctuation else 0 for c in password_hash])
        Digits = any([1 if c in string.digits else 0 for c in password_hash])

        pass_char = [UpperC, LowerC, SpecialC, Digits]
        pass_length = len(password_hash)
        strength_score = 0

        if pass_length >= 8:
            strength_score += 1
        if pass_length >= 10:
            strength_score += 1
        if pass_length >= 12:
            strength_score += 1
        if pass_length >= 14:
            strength_score += 1

        if sum(pass_char) > 1:
            strength_score += 1
        if sum(pass_char) > 2:
            strength_score += 1
        if sum(pass_char) > 3:
            strength_score += 1

    @staticmethod
    def pass_feedback(password_hash):
        strength_score = AuthService.pass_strength(password_hash)

        if strength_score < 4:
            message = ("Weak password, add a unique mix of uppercase/lowercase letters, digits, and special characters.")
        elif strength_score == 4:
            message = ("Sufficient password, consider making it longer.")
        elif 4 < strength_score < 7:
            message = ("Moderately strong password, still has room for improvement")
        else:
            message = ("Strong password!, Filled the minimum requirements.")

        return strength_score, message

    def Register(self, email, username, password_hash, confirm_pass, role = "patron", staff_code = ""):
        email = email.strip()
        username = username.strip()

        if not email or not username or not password_hash:
            return False, "All fields are required to be filled."

        if password_hash != confirm_pass:
            return False, "Passwords do not match"

        strength_score = self.pass_strength(password_hash)

        if strength_score < 4:
            message = ("Weak password, add a unique mix of uppercase/lowercase letters, digits, and special characters.")
        elif strength_score == 4:
            message = ("Sufficient password, consider making it longer.")
        elif 4 < strength_score < 7:
            message = ("Moderately strong password, still has room for improvement")
        else:
            message = ("Strong password!, Filled the minimum requirements.")

        if staff_code:
            if staff_code != staff_code:
                return False, "Incorrect staff code"
            role = "librarian"
        else:
            role = "patron"

        hashed_password = generate_password_hash(password_hash)

        user_repository = User_repo()

        if user_repository.email_exists(email):
            return False, "Email already exists."

        if user_repository.username_exist(username):
            return False, "Username already exists, try another."

        user_repository.create(
            email=email,
            username=username,
            password_hash=hashed_password,
            role=role
        )
        return True, "Account created successfully."

    def Login(self, username, password_hash):
        user_repository = User_repo()
        user = user_repository.find_username(username)

        if user is None:
            return None

        if not user.active:
            return None

        if not user.check_pass(password_hash):
            return None

        return user



            # Book data and rules
class Book: 
    def __init__(self, book_id, title, author, genre, description, available = True, catalog = True):
        self.title = title
        self.author = author
        self.genre = genre
        self.description = description
        self.available = available
        self.catalog = catalog

    def search_book(self, search_term):
        if not search_term:
            return False

        term = search_term.lower()
        fields = [self.title, self.author]

        for field in fields:
            if field and term in str(field).lower():
                return True
        return False

    def display_book_info(self):
        return f"{self.title} by {self.author}\n{self.description}"

    def borrow(self):
        if not self.available:
            return "This book is currently borrowed"

        self.available = False

        return True, "Book marked as borrowed"

    def return_book(self):
        if self.available:
            return False, "This book is already available"

        self.available = True

        return True, "Book has been recently returned and is now available"



# Settles borrow/return due dates and late/loss fees
class Loan:
    def __init__(self, loan_id, patron_id, book_id, borrowed_at, due_date, returned_at=None, late_fee=0):
        self.loan_id = loan_id
        self.patron_id = patron_id
        self.book_id = book_id
        self.borrowed_at = borrowed_at
        self.due_date = due_date
        self.returned_at = returned_at
        self.late_fee = late_fee

    def is_returned(self):
        return self.returned_at is not None

    def is_overdue(self, current_date):
        if self.is_returned():
            return self.returned_at > self.due_date
        return current_date > self.due_date

    def calculate_late_fee(self, current_date, daily_fee):
        if not self.is_overdue(current_date):
            self.late_fee = 0
            return 0

        if self.is_returned():
            end_date = self.returned_at
        else:
            end_date = current_date

        end_date = self.returned_at or current_date
        overdue = (end_date - self.due_date).days
        self.late_fee = overdue * daily_fee
        return self.late_fee

    def mark_returned(self, returned_at):
        if self.returned_at is not None:
            return
        self.returned_at = returned_at



            # Patron/Member permissions, actions and privileges
class Patr_perms:
    def borrow(self, patron, book_id):
        ...

    def return_book(self, patron, book_id):
        ...

    def pay_late_fee(self, patron, loan_id):
        ...

    def view_payments(self, patron, loan_id):
        ...

    def pay_loss(self, patron, loan_id):
        ...



            # Librarian/Staff permissions, actions, and privileges
class Lib_Perms:
    def add_book(self, librarian, book_id, title, author, genre, description):
        ...

    def edit_book(self, librarian, book_id, title, author, genre, description):
        ...

    def archive_book(self, librarian, book_id):
        ...

    def update_return_status(self, librarian, book_id):
        ...

    def manage_mem(self, librarian, user_id):
        ...

            # Database integration and its repositories 
class User_repo():
    def create(self, email, username, password_hash, role):
        ...

    def find_username(self, username):
        ...

    def email_exists(self, email):
        ...

    def username_exist(self, username):
        ...

class Book_repo():
    def create(self, book):
        ...

    def find_book(self, book_id):
        ...

    def find_all(self):
        ...

    def update_book(self, book):
        ...


class Loan_repo():
    def create_loan(self, patron_id, book_id, borrowed_at, due_date):
        ...

    def find_active_loan(self, patron_id, book_id):
        ...

    def return_record(self, loan_id, returned_at):
        ...

            # Flask routes coming soon
