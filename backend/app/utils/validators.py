import re

from .date_utils import to_date

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


def is_valid_email(email):
    return bool(EMAIL_RE.match(email))


def is_valid_username(username):
    return bool(USERNAME_RE.match(username))