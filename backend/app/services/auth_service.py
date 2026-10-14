from models.password_rule import PASSWORD_RULES
from models.user import Patron, Librarian
from utils.errors import ValidationError
from utils.security import hash_password, is_correct_staff_code
from utils.validators import is_valid_email, is_valid_username


class AuthService:
    def __init__(self, user_repo):
        self._user_repo = user_repo

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

    def register(self, email, username, password, confirm_password, code=None):
        email = (email or "").strip().lower()
        username = (username or "").strip()

        if not is_valid_email(email):
            raise ValidationError("Please enter a valid email address.")

        if not is_valid_username(username):
            raise ValidationError("Username must be 3-30 characters: letters, numbers, _ . -")

        if password != confirm_password:
            raise ValidationError("Passwords do not match.")

        tips = self.pass_feedback(password)
        if tips:
            raise ValidationError("Password too weak. " + " ".join(tips))

        if self._user_repo.email_exists(email):
            raise ValidationError("That email is already registered.")

        if self._user_repo.username_exist(username):
            raise ValidationError("That username is taken.")

        role = Patron.ROLE

        if code:
            if is_correct_staff_code(code):
                role = Librarian.ROLE
            else:
                raise ValidationError("Invalid staff code.")

        return self._user_repo.create(email, username, hash_password(password), role)

    def login(self, username, password):
        user = self._user_repo.find_username((username or "").strip())

        if user is not None and not user.active:
            raise ValidationError("This account has been deactivated. Please contact a librarian.")

        if user is None or not user.check_pass(password):
            raise ValidationError("Invalid username or password.")

        return user