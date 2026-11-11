from datetime import datetime

from sqlalchemy.exc import IntegrityError

from ..exceptions import ValidationError
from ..extensions import db
from ..models.notification_record import NotificationRecord


class NotificationRepository:
    def create(
        self,
        user_id,
        title,
        message,
        category="general",
        link=None,
        dedupe_key=None,
        commit=True,
    ):
        record = NotificationRecord(
            user_id=user_id,
            title=title,
            message=message,
            category=category,
            link=link,
            dedupe_key=dedupe_key,
        )
        db.session.add(record)
        if not commit:
            return record
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            if dedupe_key and self.exists_dedupe_key(dedupe_key):
                return None
            raise ValidationError("The notification could not be saved.") from error
        return record

    def exists_dedupe_key(self, dedupe_key):
        if not dedupe_key:
            return False
        return db.session.scalar(
            db.select(NotificationRecord.notification_id)
            .where(NotificationRecord.dedupe_key == dedupe_key)
            .limit(1)
        ) is not None

    def for_user(self, user_id, limit=100):
        return list(
            db.session.execute(
                db.select(NotificationRecord)
                .where(NotificationRecord.user_id == user_id)
                .order_by(
                    NotificationRecord.created_at.desc(),
                    NotificationRecord.notification_id.desc(),
                )
                .limit(limit)
            ).scalars()
        )

    def recent_for_user(self, user_id, limit=6):
        return self.for_user(user_id, limit=limit)

    def unread_count(self, user_id):
        return db.session.scalar(
            db.select(db.func.count(NotificationRecord.notification_id)).where(
                NotificationRecord.user_id == user_id,
                NotificationRecord.read_at.is_(None),
            )
        ) or 0

    def find_for_user(self, user_id, notification_id):
        return db.session.execute(
            db.select(NotificationRecord).where(
                NotificationRecord.user_id == user_id,
                NotificationRecord.notification_id == notification_id,
            )
        ).scalar_one_or_none()

    def mark_read(self, user_id, notification_id):
        record = self.find_for_user(user_id, notification_id)
        if record is None:
            return False
        if record.read_at is None:
            record.read_at = datetime.now()
            db.session.commit()
        return True

    def mark_all_read(self, user_id):
        db.session.execute(
            db.update(NotificationRecord)
            .where(
                NotificationRecord.user_id == user_id,
                NotificationRecord.read_at.is_(None),
            )
            .values(read_at=datetime.now())
        )
        db.session.commit()

    def users_with_role(self, role):
        from ..models.user_record import UserRecord

        return list(
            db.session.execute(
                db.select(UserRecord.user_id).where(
                    UserRecord.role == role,
                    UserRecord.active.is_(True),
                )
            ).scalars()
        )
