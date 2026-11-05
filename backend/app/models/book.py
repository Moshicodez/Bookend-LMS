from datetime import datetime, timezone

from ..config import Config
from ..exceptions import ValidationError


class Book:
    KIND = "standard"
    LOAN_DAYS = Config.LOAN_DAYS
    MAX_COPIES = 2**63 - 1
    _registry = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Book._registry[cls.KIND] = cls

    def __init__(
        self,
        book_id,
        title,
        author,
        genre,
        description,
        available=True,
        catalog=True,
        cover=None,
        archived_at=None,
        total_copies=1,
        available_copies=None,
        on_loan_copies=None,
        reserved_copies=0,
    ):
        self._book_id = book_id
        self._total_copies = self._normalize_copy_count(total_copies)
        if on_loan_copies is None:
            self._on_loan_copies = 0 if available else self._total_copies
        else:
            self._on_loan_copies = self._normalize_copy_count(on_loan_copies)
        self._reserved_copies = self._normalize_copy_count(reserved_copies)
        if available_copies is None:
            available_copies = max(
                self._total_copies - self._on_loan_copies - self._reserved_copies,
                0,
            )
        self._available_copies = self._normalize_copy_count(available_copies)
        self._catalog = bool(catalog)
        self._cover = cover
        self._archived_at = archived_at
        self._set_details(title, author, genre, description)

    @classmethod
    def create(cls, kind, *args, **kwargs):
        if kind == Book.KIND:
            book_class = Book
        else:
            book_class = cls._registry.get(kind)
        if book_class is None:
            raise ValidationError(f"Unknown book kind: {kind}")
        return book_class(*args, **kwargs)

    def _set_details(self, title, author, genre, description):
        title = (title or "").strip()
        author = (author or "").strip()

        if not title or not author:
            raise ValidationError("A book needs both a title and an author.")

        self._title = title
        self._author = author
        self._genre = (genre or "").strip()
        self._description = (description or "").strip()

    @property
    def book_id(self):
        return self._book_id

    @property
    def title(self):
        return self._title

    @property
    def author(self):
        return self._author

    @property
    def genre(self):
        return self._genre

    @property
    def description(self):
        return self._description

    @property
    def available(self):
        return self._total_copies > self._on_loan_copies

    @property
    def catalog(self):
        return self._catalog

    @property
    def total_copies(self):
        return self._total_copies

    @property
    def available_copies(self):
        return self._available_copies

    @property
    def on_loan_copies(self):
        return self._on_loan_copies

    @property
    def reserved_copies(self):
        return self._reserved_copies

    @property
    def availability_status(self):
        if not self._catalog:
            return "Archived"
        if self.KIND == "reference":
            return "In-library use" if self.available else "Out of stock"
        if self._available_copies:
            return "Available"
        if self._reserved_copies:
            return "Reserved"
        if self._on_loan_copies:
            return "On loan"
        return "Out of stock"

    @property
    def cover(self):
        return self._cover

    @property
    def archived_at(self):
        return self._archived_at

    def set_cover(self, filename):
        self._cover = filename

    @property
    def kind(self):
        return self.KIND

    @property
    def loan_days(self):
        return self.LOAN_DAYS

    def update_details(self, title, author, genre, description):
        self._set_details(title, author, genre, description)

    def search_book(self, search_term):
        term = (search_term or "").strip().lower()
        if not term:
            return True

        haystack = f"{self._title} {self._author} {self._genre}".lower()
        return all(word in haystack for word in term.split())

    def display_book_info(self):
        return {
            "book_id": self._book_id,
            "title": self._title,
            "author": self._author,
            "genre": self._genre,
            "description": self._description,
            "cover": self._cover,
            "kind": self.KIND,
            "loan_days": self.loan_days,
            "status": self.availability_status,
            "total_copies": self._total_copies,
            "available_copies": self._available_copies,
            "on_loan_copies": self._on_loan_copies,
            "reserved_copies": self._reserved_copies,
        }

    def can_borrow(self):
        return self._catalog and self._available_copies > 0

    def borrow(self, reserved=False):
        if not self._catalog:
            raise ValidationError("This book is no longer in the catalog.")
        if not reserved and not self._available_copies:
            raise ValidationError("This book is already on loan.")
        if self.KIND == "reference":
            raise ValidationError("Reference books can only be read in the library.")
        if reserved:
            self._reserved_copies = max(0, self._reserved_copies - 1)
        else:
            self._available_copies -= 1
        self._on_loan_copies += 1

    def return_book(self):
        self._on_loan_copies = max(0, self._on_loan_copies - 1)
        if self._total_copies > self._on_loan_copies + self._reserved_copies:
            self._available_copies += 1

    def archive(self):
        if self._on_loan_copies:
            raise ValidationError("This book is on loan. Process its return before archiving.")
        if self._reserved_copies:
            raise ValidationError("This book is reserved for a patron and cannot be archived.")
        self._catalog = False
        self._archived_at = datetime.now(timezone.utc).replace(tzinfo=None)

    def restore(self):
        if not self.available:
            raise ValidationError("An unavailable book cannot be restored to the catalog.")
        self._catalog = True
        self._archived_at = None

    def mark_lost(self):
        if self._total_copies == 0:
            raise ValidationError("There are no copies left to mark as lost.")
        self._total_copies = max(0, self._total_copies - 1)
        self._on_loan_copies = max(0, self._on_loan_copies - 1)
        if self._total_copies == 0:
            self._catalog = False
        self._available_copies = max(
            self._total_copies - self._on_loan_copies - self._reserved_copies,
            0,
        )

    def set_total_copies(self, total_copies):
        self._total_copies = self._normalize_copy_count(total_copies)
        self._available_copies = max(
            self._total_copies - self._on_loan_copies - self._reserved_copies,
            0,
        )

    @staticmethod
    def _normalize_copy_count(value):
        try:
            count = int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError("Copy counts must be whole numbers.") from error
        if (
            isinstance(value, bool)
            or count != value
            or count < 0
            or count > Book.MAX_COPIES
        ):
            raise ValidationError("Copy counts must be whole numbers of at least zero.")
        return count

    def to_record(self):
        return {
            "book_id": self._book_id,
            "kind": self.KIND,
            "title": self._title,
            "author": self._author,
            "genre": self._genre,
            "description": self._description,
            "cover": self._cover,
            "available": self.available,
            "catalog": self._catalog,
            "archived_at": (
                self._archived_at.isoformat() if self._archived_at else None
            ),
            "total_copies": self._total_copies,
        }


class NewReleaseBook(Book):
    KIND = "new_release"
    LOAN_DAYS = 7


class ReferenceBook(Book):
    KIND = "reference"

    def can_borrow(self):
        return False

    def borrow(self, reserved=False):
        raise ValidationError("Reference books can only be read in the library.")