import os
import string
import sqlite3

from datetime import date, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, flash, session)
from werkzeug.security import (generate_password_hash, check_password_hash)
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key'

database = "bookend.db"
staff_code = "B0ok3nd Nvr Ends!"

def db_connect():
    # initial database connection
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row



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
        # Add conditions/logic
        return check_password_hash (self.password_hash, password)

    def perms(self, permission):
        permission = {"patron" :{"search_book", "view_book", "borrow_book", "return_book", "view_loans", 
                                 "view_payments", "pay_late_fee", "pay_loss"},
                    "librarian":{"search_book", "view_book", "add_book", "edit_book", "archive_book", 
                                 "update_return_status", "manage_mem", "manage_loans"}}
        return permission in permission.get(self.role, set())

    def is_patron(self):
        # Condition if user is patron
        return self.role == "patron"

    def is_librarian(self):
        # Condition if user is librarian
        return self.role == "librarian"



            # Authentication, login, and password verification and strength
class AuthService:
    def pass_strength(password_hash):
        ...

    def pass_feedback(password_hash):
        ...

    def Register(self):
        ...

    def Login(self):
        ...



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
        ...

    def display_book_info(self):
        ...

    def borrow(self):
        ...

    def return_book(self):
        ...



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
        ...

    def is_overdue(self, current_date):
        ...

    def calculate_late_fee(self, current_date, daily_fee):
        ...

    def mark_returned(self, returned_at):
        ...



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