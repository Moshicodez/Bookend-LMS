from abc import ABC, abstractmethod

from werkzeug.security import check_password_hash

from ..exceptions import PermissionDenied, ValidationError


class User(ABC):
    ROLE = None
    PERMISSIONS = frozenset()
    _registry = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.ROLE:
            User._registry[cls.ROLE] = cls

    def __init__(
        self,
        user_id,
        email,
        username,
        password_hash,
        active=True,
    ):
        self._user_id = user_id
        self._email = email
        self._username = username
        self._password_hash = password_hash
        self._active = bool(active)

    @classmethod
    def create(
        cls,
        user_id,
        email,
        username,
        password_hash,
        role,
        active=True,
    ):
        subclass = cls._registry.get(role)
        if subclass is None:
            raise ValidationError(f"Unknown role: {role}")
        return subclass(
            user_id,
            email,
            username,
            password_hash,
            active,
        )

    @property
    def user_id(self):
        return self._user_id

    @property
    def email(self):
        return self._email

    @property
    def username(self):
        return self._username

    @property
    def role(self):
        return self.ROLE

    @property
    def active(self):
        return self._active

    @property
    def password_hash(self):
        return self._password_hash

    def check_pass(self, password):
        if not self._active or not password:
            return False
        return check_password_hash(self._password_hash, password)

    def change_password(self, old_password, new_password_hash):
        if not self.check_pass(old_password):
            raise ValidationError("Current password is incorrect.")
        self._password_hash = new_password_hash

    def activate(self):
        self._active = True

    def deactivate(self):
        self._active = False

    def perms(self, permission):
        return self._active and permission in self.PERMISSIONS

    def require(self, permission):
        if not self.perms(permission):
            raise PermissionDenied(f"You don't have permission to do that ({permission}).")

    def is_patron(self):
        return self.ROLE == "patron"

    def is_librarian(self):
        return self.ROLE == "librarian"

    @abstractmethod
    def home_endpoint(self):
        ...

    @property
    @abstractmethod
    def loan_limit(self):
        ...

    @abstractmethod
    def can_be_managed_by(self, actor):
        ...