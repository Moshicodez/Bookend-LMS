from ..extensions import db
from ..models.favorite_record import FavoriteRecord


class FavoriteRepository:
    def contains(self, user_id, book_id):
        return db.session.get(FavoriteRecord, (user_id, book_id)) is not None

    def add(self, user_id, book_id):
        db.session.add(FavoriteRecord(user_id=user_id, book_id=book_id))
        db.session.commit()

    def remove(self, user_id, book_id):
        favorite = db.session.get(FavoriteRecord, (user_id, book_id))
        if favorite is not None:
            db.session.delete(favorite)
            db.session.commit()

    def book_ids_for_user(self, user_id):
        return list(
            db.session.execute(
                db.select(FavoriteRecord.book_id)
                .where(FavoriteRecord.user_id == user_id)
                .order_by(FavoriteRecord.book_id)
            ).scalars()
        )

    def count_for_user(self, user_id):
        return db.session.scalar(
            db.select(db.func.count())
            .select_from(FavoriteRecord)
            .where(FavoriteRecord.user_id == user_id)
        ) or 0
