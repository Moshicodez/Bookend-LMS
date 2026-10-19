from .auth import auth_bp
from .books import books_bp
from .dashboard import dashboard_bp
from .loans import loans_bp
from .members import members_bp

__all__ = ["auth_bp", "books_bp", "dashboard_bp", "loans_bp", "members_bp"]