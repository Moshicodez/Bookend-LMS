from werkzeug.security import generate_password_hash

from ..exceptions import ValidationError
from ..models.password_rule import PASSWORD_RULES
from ..models.librarian import Librarian
from ..models.patron import Patron
from ..repositories.notification_repository import NotificationRepository
from .notification_service import NotificationService
from ..utils.validators import is_valid_email, is_valid_username


class AuthService:
    def __init__(self, user_repo, notification_service=None):
        self._user_repo = user_repo
        self._notifications = notification_service or NotificationService(
            NotificationRepository()
        )

    @staticmethod
    def pass_strength(password):
        password = password or ""
        score = sum(rule.passes(password) for rule in PASSWORD_RULES)

        labels = {
            0: "Very weak",
            1: "Very weak",
            2: "Weak",
            3: "Fair",
            4: "Good",
            5: "Strong"
        }

        return score, labels[score]

    @staticmethod
    def pass_feedback(password):
        password = password or ""
        return [rule.message for rule in PASSWORD_RULES if not rule.passes(password)]

    def register(self, email, username, password, confirm_password):
        email = (email or "").strip().lower()
        username = (username or "").strip()

        if not is_valid_email(email):
            raise ValidationError("Please enter a valid email address.")

        if not is_valid_username(username):
            raise ValidationError("Username must be 3-30 characters: letters, numbers, _ . -")

        if len(password or "") < 8:
            raise ValidationError("Password must be at least 8 characters.")

        if password != confirm_password:
            raise ValidationError("Passwords don't match.")

        tips = self.pass_feedback(password)
        if tips:
            raise ValidationError("Password too weak. " + " ".join(tips))

        if self._user_repo.email_exists(email):
            raise ValidationError("That email is already registered.")

        if self._user_repo.username_exist(username):
            raise ValidationError("That username is taken.")

        user = self._user_repo.create(
            email,
            username,
            generate_password_hash(password),
            Patron.ROLE,
        )
        self._notifications.notify_role(
            "librarian",
            "New member registered",
            f"{user.username} created a library account.",
            category="member",
            link=f"/members/{user.user_id}",
            dedupe_key=f"member:{user.user_id}:registered",
        )
        return user

    def create_librarian(self, email, username, password):
        email = (email or "").strip().lower()
        username = (username or "").strip()

        if not is_valid_email(email):
            raise ValidationError("Please enter a valid email address.")
        if not is_valid_username(username):
            raise ValidationError("Username must be 3-30 characters: letters, numbers, _ . -")
        score, _ = self.pass_strength(password)
        if score < len(PASSWORD_RULES):
            tips = self.pass_feedback(password)
            raise ValidationError("Password too weak. " + " ".join(tips))
        if self._user_repo.email_exists(email):
            raise ValidationError("That email is already registered.")
        if self._user_repo.username_exist(username):
            raise ValidationError("That username is taken.")

        return self._user_repo.create(
            email,
            username,
            generate_password_hash(password),
            Librarian.ROLE,
        )

    def find_email(self, email):
        return self._user_repo.find_email((email or "").strip().lower())

    def find_by_id(self, user_id):
        return self._user_repo.find_by_id(user_id)

    def reset_password(self, user_id, new_password, confirm_password):
        user = self._user_repo.find_by_id(user_id)
        if user is None:
            raise ValidationError("User not found.")
        if new_password != confirm_password:
            raise ValidationError("Passwords do not match.")
        tips = self.pass_feedback(new_password)
        if tips:
            raise ValidationError("Password too weak. " + " ".join(tips))

        self._user_repo.update_password_hash(
            user.user_id,
            generate_password_hash(new_password),
        )

    def login(self, username, password):
        login_identifier = (username or "").strip()
        user = self._user_repo.find_username(login_identifier)
        if user is None and "@" in login_identifier:
            user = self._user_repo.find_email(login_identifier.lower())

        if user is not None and not user.active:
            raise ValidationError("This account has been deactivated. Please contact a librarian.")

        if user is None or not user.check_pass(password):
            raise ValidationError("Invalid username or password.")

        return user