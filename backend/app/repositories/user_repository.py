from sqlalchemy.exc import IntegrityError

from ..exceptions import ValidationError
from ..extensions import db
from ..models.user import User
from ..models.user_record import UserRecord


class UserRepository:
    def create(self, email, username, password_hash, role):
        record = UserRecord(
            email=email,
            username=username,
            password_hash=password_hash,
            role=role,
        )
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise ValidationError(
                "An account with that username or email already exists."
            ) from error
        return self._to_domain_user(record)

    def find_username(self, username):
        record = db.session.execute(
            db.select(UserRecord).where(UserRecord.username == username)
        ).scalar_one_or_none()
        return self._to_domain_user(record) if record else None

    def email_exists(self, email):
        return db.session.execute(
            db.select(UserRecord.user_id).where(UserRecord.email == email)
        ).first() is not None

    def username_exist(self, username):
        return db.session.execute(
            db.select(UserRecord.user_id).where(UserRecord.username == username)
        ).first() is not None

    def username_exists(self, username):
        return self.username_exist(username)

    def find_all(self):
        records = db.session.execute(
            db.select(UserRecord).order_by(UserRecord.username)
        ).scalars()
        return [self._to_domain_user(record) for record in records]

    def find_by_id(self, user_id):
        record = db.session.get(UserRecord, user_id)
        return self._to_domain_user(record) if record else None

    def set_active(self, user_id, active):
        record = db.session.get(UserRecord, user_id)
        if record is None:
            raise ValidationError("User not found.")
        record.active = bool(active)
        db.session.commit()

    @staticmethod
    def _to_domain_user(record):
        return User.create(
            record.user_id,
            record.email,
            record.username,
            record.password_hash,
            record.role,
            record.active,
        )