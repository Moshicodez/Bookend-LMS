import os
import string
from werkzeug.security import generate_password_hash
from app import db
from app.models import User

STAFF_CODE = os.environ.get("STAFF_CODE")


def _pass_strength(password):
    checks = [
        any(c in string.ascii_uppercase for c in password),
        any(c in string.ascii_lowercase for c in password),
        any(c in string.punctuation     for c in password),
        any(c in string.digits          for c in password),
    ]
    score = sum(1 for n in (8, 10, 12, 14) if len(password) >= n)
    score += sum(1 for t in (1, 2, 3) if sum(checks) > t)
    return score


def pass_feedback(password):
    score = _pass_strength(password)
    if score < 4:
        msg = "Weak — add uppercase, lowercase, digits, and special characters."
    elif score == 4:
        msg = "Sufficient — consider making it longer."
    elif score < 7:
        msg = "Moderately strong — still has room for improvement."
    else:
        msg = "Strong password!"
    return score, msg


def register(email, username, password, confirm_pass, provided_code=""):
    email    = email.strip()
    username = username.strip()

    if not email or not username or not password:
        return False, "All fields are required."

    if password != confirm_pass:
        return False, "Passwords do not match."

    score, msg = pass_feedback(password)
    if score < 4:
        return False, msg

    role = "librarian" if (provided_code and provided_code == STAFF_CODE) else "patron"
    if provided_code and role != "librarian":
        return False, "Incorrect staff code."

    if User.query.filter_by(email=email).first():
        return False, "Email already exists."

    if User.query.filter_by(username=username).first():
        return False, "Username already taken."

    user = User(
        email=email,
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
    )
    db.session.add(user)
    db.session.commit()
    return True, "Account created successfully."


def login(username, password):
    user = User.query.filter_by(username=username).first()
    if user and user.active and user.check_pass(password):
        return user
    return None
