from datetime import datetime

from ..exceptions import NotFoundError, ValidationError
from ..models.book import Book
from ..repositories.notification_repository import NotificationRepository
from ..repositories.reservation_repository import ReservationRepository
from .cover_service import CoverService
from .notification_service import NotificationService


class BookService:
    def __init__(self, book_repo, reservation_repo=None, notification_service=None):
        self._book_repo = book_repo
        self._reservations = reservation_repo or ReservationRepository()
        self._notifications = notification_service or NotificationService(
            NotificationRepository()
        )
        self._covers = CoverService()

    def _get_book(self, book_id):
        book = self._book_repo.find_book(book_id)

        if book is None:
            raise NotFoundError("Book not found.")

        return book

    def search_books(self, search_term="", genre=None):
        books = list(self._book_repo.find_all())

        if search_term:
            books = [book for book in books if book.search_book(search_term)]
        if genre:
            books = [
                book for book in books
                if (book.genre or "").casefold() == genre.casefold()
            ]
        return books

    def search_page(self, term="", genre="", status="", sort="title", page=1, per_page=12):
        return self._book_repo.search(term, genre, status, sort, page, per_page)

    def catalog_genre_counts(self):
        return self._book_repo.genre_counts()

    def management_search(self, librarian, term="", status="all"):
        librarian.require("edit_book")
        if status not in {
            "all",
            "available",
            "on_loan",
            "out_of_stock",
            "archived",
        }:
            status = "all"
        books, _ = self._book_repo.search(term, "", status, "title", 1, 500)
        return books

    def archived_books(self, librarian):
        librarian.require("archive_book")
        return self._book_repo.find_archived()

    def management_books(self, librarian):
        librarian.require("edit_book")
        return self._book_repo.find_all(include_archived=True)

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

    def more_in_genre(self, book):
        return self._book_repo.find_more_in_genre(book.genre, book.book_id)

    def add_book(
        self,
        librarian,
        title,
        author,
        genre,
        description,
        kind="standard",
        cover_file=None,
        total_copies=1,
    ):
        librarian.require("add_book")

        book = Book.create(
            kind,
            None,
            title,
            author,
            genre,
            description,
            total_copies=self._copy_count(total_copies),
        )
        filename = self._covers.save(cover_file)
        book.set_cover(filename)
        saved = False
        try:
            result = self._book_repo.create(book)
            saved = True
            self._notifications.notify_role(
                "librarian",
                "Book added to the catalog",
                f"{result.title} is now in the catalog.",
                category="book",
                link=f"/books/{result.book_id}",
                dedupe_key=f"book:{result.book_id}:added",
            )
            self._notifications.notify_inventory_transition(
                result,
                None,
                f"book:{result.book_id}:initial-inventory",
            )
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
        kind=None,
        total_copies=None,
    ):
        librarian.require("edit_book")
        current_book = self._get_book(book_id)
        previous_available = current_book.available_copies
        book = Book.create(
            current_book.kind if kind is None else kind,
            current_book.book_id,
            current_book.title,
            current_book.author,
            current_book.genre,
            current_book.description,
            available=current_book.available,
            catalog=current_book.catalog,
            cover=current_book.cover,
            archived_at=current_book.archived_at,
            total_copies=current_book.total_copies,
            available_copies=current_book.available_copies,
            on_loan_copies=current_book.on_loan_copies,
            reserved_copies=current_book.reserved_copies,
        )

        book.update_details(title, author, genre, description)
        if total_copies is not None:
            book.set_total_copies(self._copy_count(total_copies))
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
        if total_copies is not None:
            self._reservations.promote_waiting(book_id)

        self._notifications.notify_role(
            "librarian",
            "Book details updated",
            f"The catalog details for {book.title} were updated.",
            category="book",
            link=f"/books/{book.book_id}",
        )
        if total_copies is not None:
            self._notifications.notify_inventory_transition(
                book,
                previous_available,
                (
                    f"book:{book.book_id}:inventory:"
                    f"{datetime.now().isoformat(timespec='microseconds')}"
                ),
            )
        return book

    def archive_book(self, librarian, book_id):
        return self._archive_book(librarian, book_id, "Book archived")

    def delete_book(self, librarian, book_id):
        return self._archive_book(librarian, book_id, "Book deleted")

    def _archive_book(self, librarian, book_id, notification_title):
        librarian.require("archive_book")
        book = self._get_book(book_id)
        if self._reservations.find_ready_for_book(book_id):
            raise ValidationError(
                "This book is reserved for a patron and cannot be archived."
            )

        book.archive()
        self._book_repo.update_book(book)
        self._notifications.notify_role(
            "librarian",
            notification_title,
            f"{notification_title}: {book.title} was removed from the catalog."
            if notification_title == "Book deleted"
            else f"{book.title} was archived from the catalog.",
            category="book",
            link="/books/archived",
        )

        return book

    def restore_book(self, librarian, book_id):
        librarian.require("archive_book")
        book = self._get_book(book_id)
        if book.catalog:
            raise ValidationError("This book is already in the catalog.")
        book.restore()
        self._book_repo.update_book(book)
        self._notifications.notify_role(
            "librarian",
            "Book restored",
            f"{book.title} was restored to the catalog.",
            category="book",
            link=f"/books/{book.book_id}",
        )
        return book

    @staticmethod
    def _copy_count(value):
        try:
            count = int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError("Total copies must be a whole number.") from error
        if (
            isinstance(value, bool)
            or str(value).strip() != str(count)
            or count < 0
            or count > Book.MAX_COPIES
        ):
            raise ValidationError("Total copies must be zero or more.")
        return count

    def mark_book_lost(self, librarian, book_id):
        librarian.require("update_return_status")
        book = self._get_book(book_id)

        book.mark_lost()
        self._book_repo.update_book(book)

        return book