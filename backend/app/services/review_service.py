from ..exceptions import NotFoundError, ValidationError
from ..repositories.notification_repository import NotificationRepository
from .notification_service import NotificationService


class ReviewService:
    def __init__(self, review_repository, book_repository, notification_service=None):
        self._reviews = review_repository
        self._books = book_repository
        self._notifications = notification_service or NotificationService(
            NotificationRepository()
        )

    @staticmethod
    def _validated(rating, comment):
        try:
            rating = int(rating)
        except (TypeError, ValueError) as error:
            raise ValidationError("Choose a rating from 1 to 5 stars.") from error
        if not 1 <= rating <= 5:
            raise ValidationError("Choose a rating from 1 to 5 stars.")
        comment = (comment or "").strip()
        if len(comment) > 2000:
            raise ValidationError("A review must be 2,000 characters or fewer.")
        return rating, comment

    def for_book(self, book_id):
        return self._reviews.find_for_book(book_id)

    def own_review(self, patron, book_id):
        patron.require("write_review")
        return self._reviews.find_by_user_and_book(patron.user_id, book_id)

    def summaries(self, book_ids=None):
        return self._reviews.summaries(book_ids)

    def summary(self, book_id):
        return self.summaries([book_id]).get(
            book_id, {"average": 0.0, "count": 0}
        )

    def create(self, patron, book_id, rating, comment):
        patron.require("write_review")
        book = self._books.find_book(book_id)
        if book is None or not book.catalog:
            raise NotFoundError("Book not found.")
        if self._reviews.find_by_user_and_book(patron.user_id, book_id):
            raise ValidationError("You have already reviewed this book.")
        rating, comment = self._validated(rating, comment)
        return self._reviews.create(patron.user_id, book_id, rating, comment)

    def update(self, patron, review_id, rating, comment):
        patron.require("write_review")
        review = self._owned_review(patron, review_id)
        rating, comment = self._validated(rating, comment)
        return self._reviews.update(review, rating, comment)

    def book_for_own_review(self, patron, review_id):
        patron.require("write_review")
        return self._owned_review(patron, review_id).book_id

    def delete_own(self, patron, review_id):
        patron.require("write_review")
        review = self._owned_review(patron, review_id)
        book_id = review.book_id
        self._reviews.delete(review)
        self._notify_review_deleted(review)
        return book_id

    def _owned_review(self, patron, review_id):
        review = self._reviews.find(review_id)
        if review is None or review.user_id != patron.user_id:
            raise NotFoundError("Review not found.")
        return review

    def all_reviews(self, librarian):
        librarian.require("manage_reviews")
        return self._reviews.find_all()

    def delete_any(self, librarian, review_id):
        librarian.require("manage_reviews")
        review = self._reviews.find(review_id)
        if review is None:
            raise NotFoundError("Review not found.")
        self._reviews.delete(review)
        self._notify_review_deleted(review)

    def _notify_review_deleted(self, review):
        book = self._books.find_book(review.book_id)
        title = book.title if book else "a book"
        message = f"A review of {title} was removed."
        self._notifications.notify(
            review.user_id,
            "Review deleted",
            f"Your review of {title} was deleted.",
            category="review",
            link=f"/books/{review.book_id}",
        )
        self._notifications.notify_role(
            "librarian",
            "Review deleted",
            message,
            category="review",
            link="/librarian/reviews",
        )
