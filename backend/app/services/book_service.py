from models.book import Book
from utils.exceptions import NotFoundError, ValidationError


class BookService:
    def __init__(self, book_repo):
        self._book_repo = book_repo

    def _get_book(self, book_id):
        book = self._book_repo.find_book(book_id)

        if book is None:
            raise NotFoundError("Book not found.")

        return book

    def search_books(self, search_term=""):
        books = self._book_repo.find_all()

        if not search_term:
            return books

        return [book for book in books if book.search_book(search_term)]

    def get_book(self, book_id):
        return self._get_book(book_id)

    def add_book(self, librarian, title, author, genre, description, kind="standard"):
        librarian.require("add_book")

        book = Book.create(kind, None, title, author, genre, description)
        return self._book_repo.create(book)

    def edit_book(self, librarian, book_id, title, author, genre, description):
        librarian.require("edit_book")
        book = self._get_book(book_id)

        book.update_details(title, author, genre, description)
        self._book_repo.update_book(book)

        return book

    def archive_book(self, librarian, book_id):
        librarian.require("archive_book")
        book = self._get_book(book_id)

        book.archive()
        self._book_repo.update_book(book)

        return book

    def mark_book_lost(self, librarian, book_id):
        librarian.require("update_return_status")
        book = self._get_book(book_id)

        book.mark_lost()
        self._book_repo.update_book(book)

        return book