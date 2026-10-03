from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app import db
from app.models import Book

books_bp = Blueprint("books", __name__)


@books_bp.route("/")
@books_bp.route("/books")
def index():
    search = request.args.get("q", "")
    if search:
        books = Book.query.filter(
            (Book.title.ilike(f"%{search}%")) | (Book.author.ilike(f"%{search}%"))
        ).filter_by(catalog=True).all()
    else:
        books = Book.query.filter_by(catalog=True).all()
    return render_template("books/index.html", books=books, search=search)


@books_bp.route("/books/add", methods=["GET", "POST"])
def add():
    # TODO: librarian only
    if request.method == "POST":
        book = Book(
            title=request.form.get("title"),
            author=request.form.get("author"),
            genre=request.form.get("genre"),
            description=request.form.get("description"),
        )
        db.session.add(book)
        db.session.commit()
        flash("Book added.", "success")
        return redirect(url_for("books.index"))
    return render_template("books/add.html")


@books_bp.route("/books/edit/<int:book_id>", methods=["GET", "POST"])
def edit(book_id):
    # TODO: librarian only
    book = Book.query.get_or_404(book_id)
    if request.method == "POST":
        book.title       = request.form.get("title")
        book.author      = request.form.get("author")
        book.genre       = request.form.get("genre")
        book.description = request.form.get("description")
        db.session.commit()
        flash("Book updated.", "success")
        return redirect(url_for("books.index"))
    return render_template("books/edit.html", book=book)


@books_bp.route("/books/archive/<int:book_id>")
def archive(book_id):
    # TODO: librarian only
    book = Book.query.get_or_404(book_id)
    book.catalog = False
    db.session.commit()
    flash("Book archived.", "success")
    return redirect(url_for("books.index"))
