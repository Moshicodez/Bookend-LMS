from ..config import Config
from ..exceptions import ValidationError


class Book:
    KIND = "standard"
    LOAN_DAYS = Config.LOAN_DAYS
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
        total_stock=1,
        borrowed_stock=None,
    ):
        self._book_id = book_id
        self._total_stock = self._validated_stock(total_stock)
        self._borrowed_stock = (
            self._total_stock - (1 if available else 0)
            if borrowed_stock is None
            else self._validated_stock(borrowed_stock)
        )
        self._available = bool(
            available and self._total_stock > self._borrowed_stock
        )
        self._catalog = bool(catalog)
        self._cover = cover
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
        return self._available

    @property
    def catalog(self):
        return self._catalog

    @property
    def cover(self):
        return self._cover

    @property
    def total_stock(self):
        return self._total_stock

    @property
    def borrowed_stock(self):
        return self._borrowed_stock

    @property
    def available_stock(self):
        return max(self._total_stock - self._borrowed_stock, 0)

    def set_cover(self, filename):
        self._cover = filename

    def set_total_stock(self, value):
        total_stock = self._validated_stock(value)
        if total_stock < self._borrowed_stock:
            raise ValidationError(
                f"Total stock cannot be lower than the {self._borrowed_stock} copies currently on loan."
            )
        self._total_stock = total_stock
        self._available = self.available_stock > 0

    @staticmethod
    def _validated_stock(value):
        if isinstance(value, bool):
            raise ValidationError("Stock must be a whole number greater than or equal to zero.")
        try:
            stock = int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "Stock must be a whole number greater than or equal to zero."
            ) from error
        if stock < 0 or str(value).strip() != str(stock):
            raise ValidationError("Stock must be a whole number greater than or equal to zero.")
        return stock

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
        elif self.KIND == "reference":
            status = "In-library use"
        elif self.available_stock > 0 and self._available:
            status = "Available"
        elif self.borrowed_stock:
            status = "On loan"
        else:
            status = "Unavailable"

        return {
            "book_id": self._book_id,
            "title": self._title,
            "author": self._author,
            "genre": self._genre,
            "description": self._description,
            "cover": self._cover,
            "kind": self.KIND,
            "loan_days": self.loan_days,
            "total_stock": self.total_stock,
            "borrowed_stock": self.borrowed_stock,
            "available_stock": self.available_stock,
            "status": status
        }

    def can_borrow(self):
        return (
            self._catalog
            and self.KIND != "reference"
            and self._available
            and self.available_stock > 0
        )

    def borrow(self):
        if not self._catalog:
            raise ValidationError("This book is no longer in the catalog.")
        if self.KIND == "reference":
            raise ValidationError("Reference books can only be read in the library.")
        if self.available_stock <= 0 or not self._available:
            raise ValidationError(
                "This book is currently unavailable because there are no copies in stock."
            )
        self._borrowed_stock += 1
        self._available = self.available_stock > 0

    def return_book(self):
        if self._borrowed_stock > 0:
            self._borrowed_stock -= 1
        self._available = self.available_stock > 0

    def archive(self):
        if self._borrowed_stock:
            raise ValidationError("This book is on loan. Process its return before archiving.")
        self._catalog = False

    def restore(self):
        self._catalog = True

    def mark_lost(self):
        if self._borrowed_stock:
            self._borrowed_stock -= 1
        if self._total_stock:
            self._total_stock -= 1
        self._available = self.available_stock > 0
        if self._total_stock == 0:
            self._catalog = False

    def to_record(self):
        return {
            "book_id": self._book_id,
            "kind": self.KIND,
            "title": self._title,
            "author": self._author,
            "genre": self._genre,
            "description": self._description,
            "cover": self._cover,
            "total_stock": self._total_stock,
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