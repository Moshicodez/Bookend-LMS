from ..extensions import db


class UserRecord(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False)
    username = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.CheckConstraint("role IN ('patron', 'librarian')", name="valid_user_role"),
        db.Index("uq_users_email_lower", db.func.lower(email), unique=True),
        db.Index("uq_users_username_lower", db.func.lower(username), unique=True),
    )
