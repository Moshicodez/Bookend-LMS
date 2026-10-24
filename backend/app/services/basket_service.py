from ..exceptions import NotFoundError, ValidationError


class BasketService:
    def __init__(self, book_repository, loan_repository):
        self._books = book_repository
        self._loans = loan_repository

    def add(self, patron, basket_ids, book_id):
        patron.require("borrow_book")
        try:
            book_id = int(book_id)
            basket_ids = list(dict.fromkeys(int(value) for value in basket_ids))
        except (TypeError, ValueError) as error:
            raise ValidationError("The borrow basket contains an invalid book.") from error

        if book_id in basket_ids:
            return basket_ids
        book = self._books.find_book(book_id)
        if book is None or not book.catalog:
            raise NotFoundError("Book not found.")
        if not book.can_borrow():
            raise ValidationError("This book is not currently available to borrow.")

        loans = self._loans.find_patron_loans(patron.user_id)
        active_count = sum(not loan.is_returned() for loan in loans)
        remaining = patron.loan_limit - active_count
        if len(basket_ids) >= remaining:
            raise ValidationError("Your borrow basket cannot exceed your remaining loan limit.")
        if any(loan.outstanding() > 0 for loan in loans):
            raise ValidationError("Please settle your outstanding fees before borrowing.")
        return [*basket_ids, book_id]

    @staticmethod
    def remove(basket_ids, selected_ids):
        selected = {str(value) for value in selected_ids}
        return [value for value in basket_ids if str(value) not in selected]

    def books(self, patron, basket_ids):
        patron.require("borrow_book")
        books = []
        for value in basket_ids:
            try:
                book_id = int(value)
            except (TypeError, ValueError):
                continue
            book = self._books.find_book(book_id)
            if book is not None and book.catalog:
                books.append(book)
        return books
