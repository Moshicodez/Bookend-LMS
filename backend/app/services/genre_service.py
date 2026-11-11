from ..exceptions import NotFoundError, ValidationError
from ..repositories.notification_repository import NotificationRepository
from ..constants import UNCATEGORIZED
from .notification_service import NotificationService


class GenreService:
    def __init__(self, genre_repository, notification_service=None):
        self._genres = genre_repository
        self._notifications = notification_service or NotificationService(
            NotificationRepository()
        )

    def list_genres(self):
        return self._genres.list_genres()

    def manage_genres(self, librarian):
        librarian.require("manage_genres")
        return self._genres.list_for_management()

    def add_genre(self, librarian, name):
        librarian.require("manage_genres")
        name = (name or "").strip()
        if not name:
            raise ValidationError("Enter a genre name.")
        if len(name) > 100:
            raise ValidationError("Genre names must be 100 characters or fewer.")
        if name.casefold() == UNCATEGORIZED.casefold():
            raise ValidationError(
                f"'{UNCATEGORIZED}' is reserved for books without a genre."
            )
        if any(existing.casefold() == name.casefold() for existing in self._genres.list_genres()):
            raise ValidationError("A genre with this name already exists.")
        return self._genres.add(name)

    def remove_genre(self, librarian, name):
        librarian.require("manage_genres")
        name = (name or "").strip()
        if not name or not any(
            existing.casefold() == name.casefold()
            for existing in self._genres.list_genres()
        ):
            raise NotFoundError("Genre not found.")
        book_count = self._genres.remove(name)
        if book_count is False:
            raise NotFoundError("Genre not found.")
        self._notifications.notify_role(
            "librarian",
            "Genre removed",
            f"Genre removed: {name} ({book_count} books {UNCATEGORIZED.lower()}).",
            category="genre",
            link="/librarian/genres/",
        )
        return book_count
