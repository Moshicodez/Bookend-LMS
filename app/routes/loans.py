from datetime import date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, session
from app import db
from app.models import Book, Loan

loans_bp = Blueprint("loans", __name__)

LOAN_DAYS   = 14
DAILY_FEE   = 5.00


@loans_bp.route("/borrow/<int:book_id>")
def borrow(book_id):
    # TODO: patron only
    book = Book.query.get_or_404(book_id)
    ok, msg = book.borrow()
    if ok:
        loan = Loan(
            patron_id=session.get("user_id"),
            book_id=book.book_id,
            borrowed_at=date.today(),
            due_date=date.today() + timedelta(days=LOAN_DAYS),
        )
        db.session.add(loan)
        db.session.commit()
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("books.index"))


@loans_bp.route("/return/<int:loan_id>")
def return_book(loan_id):
    # TODO: patron only
    loan = Loan.query.get_or_404(loan_id)
    loan.mark_returned()
    ok, msg = loan.book.return_book()
    loan.calculate_late_fee(daily_fee=DAILY_FEE)
    db.session.commit()
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("loans.dashboard"))


@loans_bp.route("/dashboard")
def dashboard():
    # TODO: patron only
    loans = Loan.query.filter_by(patron_id=session.get("user_id")).all()
    return render_template("loans/dashboard.html", loans=loans, today=date.today())


@loans_bp.route("/pay/<int:loan_id>")
def pay(loan_id):
    # TODO: patron only
    loan = Loan.query.get_or_404(loan_id)
    loan.late_fee = 0.0
    db.session.commit()
    flash("Late fee paid.", "success")
    return redirect(url_for("loans.dashboard"))
