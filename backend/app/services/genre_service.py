from ..exceptions import NotFoundError, ValidationError


class GenreService:
    def __init__(self, genre_repository):
        self._genres = genre_repository

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
        if self._genres.books_use_genre(name):
            raise ValidationError(
                "Reassign or clear books in this genre before removing it."
            )
        if not self._genres.remove(name):
            raise NotFoundError("Genre not found.")
