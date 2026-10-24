from sqlalchemy.exc import IntegrityError

from ..exceptions import ValidationError
from ..extensions import db
from ..models.book_record import BookRecord
from ..models.review_record import ReviewRecord
from ..models.user_record import UserRecord


class ReviewRepository:
    def create(self, user_id, book_id, rating, comment):
        review = ReviewRecord(
            user_id=user_id,
            book_id=book_id,
            rating=rating,
            comment=comment,
        )
        db.session.add(review)
        self._commit()
        return review

    def find_for_book(self, book_id):
        rows = db.session.execute(
            db.select(ReviewRecord, UserRecord.username)
            .join(UserRecord, UserRecord.user_id == ReviewRecord.user_id)
            .where(ReviewRecord.book_id == book_id)
            .order_by(ReviewRecord.created_at.desc(), ReviewRecord.review_id.desc())
        ).all()
        return [{"review": review, "username": username} for review, username in rows]

    def find_by_user_and_book(self, user_id, book_id):
        return db.session.execute(
            db.select(ReviewRecord).where(
                ReviewRecord.user_id == user_id,
                ReviewRecord.book_id == book_id,
            )
        ).scalar_one_or_none()

    def find(self, review_id):
        return db.session.get(ReviewRecord, review_id)

    def update(self, review, rating, comment):
        review.rating = rating
        review.comment = comment
        self._commit()
        return review

    def delete(self, review):
        db.session.delete(review)
        db.session.commit()

    def summaries(self, book_ids=None):
        statement = db.select(
            ReviewRecord.book_id,
            db.func.avg(ReviewRecord.rating),
            db.func.count(ReviewRecord.review_id),
        ).group_by(ReviewRecord.book_id)
        if book_ids is not None:
            if not book_ids:
                return {}
            statement = statement.where(ReviewRecord.book_id.in_(book_ids))
        return {
            book_id: {"average": float(average), "count": count}
            for book_id, average, count in db.session.execute(statement).all()
        }

    def find_all(self):
        rows = db.session.execute(
            db.select(ReviewRecord, UserRecord.username, BookRecord.title)
            .join(UserRecord, UserRecord.user_id == ReviewRecord.user_id)
            .join(BookRecord, BookRecord.book_id == ReviewRecord.book_id)
            .order_by(ReviewRecord.created_at.desc(), ReviewRecord.review_id.desc())
        ).all()
        return [
            {"review": review, "username": username, "book_title": title}
            for review, username, title in rows
        ]

    @staticmethod
    def _commit():
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError(
                "A review could not be saved. Check the rating and try again."
            ) from error
