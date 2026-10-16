import re
from datetime import date


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


def is_valid_email(email):
    return bool(EMAIL_RE.match(email))


def is_valid_username(username):
    return bool(USERNAME_RE.match(username))


def to_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])