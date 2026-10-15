import re
from datetime import date
from hmac import compare_digest

from ..config import Config


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


def is_valid_email(email):
    return bool(EMAIL_RE.match(email))


def is_valid_username(username):
    return bool(USERNAME_RE.match(username))


def is_correct_staff_code(code):
    expected_code = Config.STAFF_CODE
    return bool(code and expected_code) and compare_digest(code, expected_code)


def to_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])