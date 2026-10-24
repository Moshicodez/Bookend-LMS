from ..exceptions import NotFoundError, ValidationError
from ..models.book import Book
from .cover_service import CoverService


class BookService:
    def __init__(self, book_repo):
        self._book_repo = book_repo
        self._covers = CoverService()

    def _get_book(self, book_id):
        book = self._book_repo.find_book(book_id)

        if book is None:
            raise NotFoundError("Book not found.")

        return book

    def search_books(self, search_term="", genre=None):
        books = self._book_repo.find_all()

        if search_term:
            books = [book for book in books if book.search_book(search_term)]
        if genre:
            books = [
                book for book in books
                if (book.genre or "").casefold() == genre.casefold()
            ]
        return books

    def archived_books(self, librarian):
        librarian.require("archive_book")
        return self._book_repo.find_archived()

    def seed_demo(self, books):
        seeded_count = 0
        for item in books:
            if not isinstance(item, dict):
                raise ValidationError("Demo book entries must be objects.")

            title = item.get("title", "")
            author = item.get("author", "")
            if self._book_repo.find_by_title_author(title, author) is not None:
                continue

            book = Book(None, title, author, item.get("genre", ""), item.get("description", ""))
            self._book_repo.create(book)
            seeded_count += 1

        return seeded_count

    def get_book(self, book_id):
        return self._get_book(book_id)

    def add_book(
        self,
        librarian,
        title,
        author,
        genre,
        description,
        kind="standard",
        cover_file=None,
    ):
        librarian.require("add_book")

        book = Book.create(kind, None, title, author, genre, description)
        filename = self._covers.save(cover_file)
        book.set_cover(filename)
        saved = False
        try:
            result = self._book_repo.create(book)
            saved = True
            return result
        finally:
            if not saved:
                self._covers.delete(filename)

    def edit_book(
        self,
        librarian,
        book_id,
        title,
        author,
        genre,
        description,
        cover_file=None,
    ):
        librarian.require("edit_book")
        book = self._get_book(book_id)

        book.update_details(title, author, genre, description)
        previous_cover = book.cover
        filename = self._covers.save(cover_file)
        if filename:
            book.set_cover(filename)
        saved = False
        try:
            self._book_repo.update_book(book)
            saved = True
        finally:
            if not saved:
                self._covers.delete(filename)
        if filename:
            self._covers.delete(previous_cover)

        return book

    def archive_book(self, librarian, book_id):
        librarian.require("archive_book")
        book = self._get_book(book_id)

        book.archive()
        self._book_repo.update_book(book)

        return book

    def restore_book(self, librarian, book_id):
        librarian.require("archive_book")
        book = self._get_book(book_id)
        if book.catalog:
            raise ValidationError("This book is already in the catalog.")
        book.restore()
        self._book_repo.update_book(book)
        return book

    def mark_book_lost(self, librarian, book_id):
        librarian.require("update_return_status")
        book = self._get_book(book_id)

        book.mark_lost()
        self._book_repo.update_book(book)

        return book