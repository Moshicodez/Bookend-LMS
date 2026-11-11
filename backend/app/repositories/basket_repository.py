from ..extensions import db
from ..models.basket_record import BasketRecord


class BasketRepository:
    def book_ids_for_user(self, user_id):
        return list(
            db.session.execute(
                db.select(BasketRecord.book_id)
                .where(BasketRecord.user_id == user_id)
                .order_by(BasketRecord.created_at, BasketRecord.book_id)
            ).scalars()
        )

    def replace_for_user(self, user_id, book_ids):
        db.session.execute(
            db.delete(BasketRecord).where(BasketRecord.user_id == user_id)
        )
        db.session.add_all(
            BasketRecord(user_id=user_id, book_id=book_id)
            for book_id in dict.fromkeys(book_ids)
        )
        db.session.commit()

    def remove_books(self, user_id, book_ids):
        db.session.execute(
            db.delete(BasketRecord).where(
                BasketRecord.user_id == user_id,
                BasketRecord.book_id.in_(book_ids),
            )
        )
        db.session.commit()

    def clear_for_user(self, user_id):
        db.session.execute(
            db.delete(BasketRecord).where(BasketRecord.user_id == user_id)
        )
        db.session.commit()
