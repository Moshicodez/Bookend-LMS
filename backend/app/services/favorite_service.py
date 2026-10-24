from ..exceptions import NotFoundError


class FavoriteService:
    def __init__(self, favorite_repository, book_repository):
        self._favorites = favorite_repository
        self._books = book_repository

    def toggle(self, patron, book_id):
        patron.require("save_favorites")
        book = self._books.find_book(book_id)
        if book is None or not book.catalog:
            raise NotFoundError("Book not found.")
        if self._favorites.contains(patron.user_id, book_id):
            self._favorites.remove(patron.user_id, book_id)
            return False
        self._favorites.add(patron.user_id, book_id)
        return True

    def book_ids(self, patron):
        patron.require("save_favorites")
        return self._favorites.book_ids_for_user(patron.user_id)

    def books(self, patron):
        ids = self.book_ids(patron)
        return [
            book
            for book_id in ids
            if (book := self._books.find_book(book_id)) is not None and book.catalog
        ]

    def count(self, patron_id):
        return self._favorites.count_for_user(patron_id)
