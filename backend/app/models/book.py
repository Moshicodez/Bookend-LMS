from config import Config

from utils.errors import ValidationError # still needs fix


class Book:
    KIND = "standard"
    LOAN_DAYS = Config.LOAN_DAYS
    _registry = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        Book._registry[cls.KIND] = cls

    def __init__(self, book_id, title, author, genre, description, available=True, catalog=True):
        self._book_id = book_id
        self._available = bool(available)
        self._catalog = bool(catalog)
        self._set_details(title, author, genre, description)

    @classmethod
    def create(cls, kind, *args, **kwargs):
        return cls._registry.get(kind, Book)(*args, **kwargs)

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
        return self._available

    @property
    def catalog(self):
        return self._catalog

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
        if not self._catalog:
            status = "Archived"
        elif self._available:
            status = "Available"
        else:
            status = "On loan"

        return {
            "book_id": self._book_id,
            "title": self._title,
            "author": self._author,
            "genre": self._genre,
            "description": self._description,
            "kind": self.KIND,
            "loan_days": self.loan_days,
            "status": status
        }

    def can_borrow(self):
        return self._catalog and self._available

    def borrow(self):
        if not self._catalog:
            raise ValidationError("This book is no longer in the catalog.")
        if not self._available:
            raise ValidationError("This book is already on loan.")
        self._available = False

    def return_book(self):
        self._available = True

    def archive(self):
        if not self._available:
            raise ValidationError("This book is on loan. Process its return before archiving.")
        self._catalog = False

    def mark_lost(self):
        self._available = False
        self._catalog = False

    def to_record(self):
        return {
            "book_id": self._book_id,
            "kind": self.KIND,
            "title": self._title,
            "author": self._author,
            "genre": self._genre,
            "description": self._description,
            "available": self._available,
            "catalog": self._catalog
        }


class NewReleaseBook(Book):
    KIND = "new_release"
    LOAN_DAYS = 7


class ReferenceBook(Book):
    KIND = "reference"

    def can_borrow(self):
        return False

    def borrow(self):
        raise ValidationError("Reference books can only be read in the library.")