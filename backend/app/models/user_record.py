from ..extensions import db


class UserRecord(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254, collation="NOCASE"), nullable=False, unique=True)
    username = db.Column(db.String(30, collation="NOCASE"), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.CheckConstraint("role IN ('patron', 'librarian')", name="valid_user_role"),
    )
