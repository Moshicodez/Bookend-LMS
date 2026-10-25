import json
import os

import click
from flask import Flask, session

from .config import COVER_COLORS, Config
from .csrf import CSRFProtect
from .exceptions import NotFoundError, PermissionDenied, ValidationError
from .extensions import db


def create_app(test_config=None):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, "frontend", "templates"),
        static_folder=os.path.join(project_root, "frontend", "static"),
    )
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    CSRFProtect().init_app(app)

    from .models import BookRecord, GenreRecord, LoanRecord, Librarian, Patron, UserRecord
    from .routes.auth import auth_bp
    from .routes.books import books_bp
    from .routes.dashboard import dashboard_bp
    from .routes.genres import genres_bp
    from .routes.landing import landing_bp
    from .routes.loans import loans_bp
    from .routes.members import members_bp
    from .routes.patron import patron_bp
    from .routes.social import social_bp
    from .schema_migrations import upgrade_legacy_sqlite_schema
    from .services.auth_service import AuthService
    from .services.book_service import BookService
    from .repositories.book_repository import BookRepository
    from .repositories.favorite_repository import FavoriteRepository
    from .repositories.genre_repository import GenreRepository
    from .repositories.loan_repository import LoanRepository
    from .repositories.user_repository import UserRepository

    with app.app_context():
        db.create_all()
        upgrade_legacy_sqlite_schema()

    app.register_blueprint(landing_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(genres_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(patron_bp)

    @app.context_processor
    def library_navigation_context():
        from .routes.auth import _signed_in_user

        current_user = _signed_in_user()
        favorite_ids = set()
        favorite_count = 0
        basket_count = 0
        overdue_count = 0
        if current_user is not None and current_user.is_patron():
            favorite_ids = set(
                FavoriteRepository().book_ids_for_user(current_user.user_id)
            )
            favorite_count = len(favorite_ids)
            basket_ids = session.get("basket_book_ids", [])
            basket_count = len(set(basket_ids)) if isinstance(basket_ids, list) else 0
        elif current_user is not None and current_user.is_librarian():
            overdue_count = len(LoanRepository().find_overdue())
        return {
            "current_user": current_user,
            "favorite_ids": favorite_ids,
            "favorite_count": favorite_count,
            "basket_count": basket_count,
            "overdue_count": overdue_count,
            "navigation_genres": GenreRepository().list_genres(),
            "cover_colors": COVER_COLORS,
        }

    @app.cli.command("create-librarian")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    def create_librarian_command(username, email):
        """Create an active librarian account."""
        password = click.prompt(
            "Password",
            hide_input=True,
            confirmation_prompt=True,
        )
        try:
            librarian = AuthService(UserRepository()).create_librarian(
                email,
                username,
                password,
            )
        except ValidationError as error:
            raise click.ClickException(str(error)) from error

        click.echo(f"Librarian account created for {librarian.username}.")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Load demo books from the static genre data file."""
        seed_path = os.path.join(
            app.static_folder,
            "data",
            "genre-books.json",
        )
        try:
            with open(seed_path, encoding="utf-8") as seed_file:
                seed_data = json.load(seed_file)
        except (OSError, json.JSONDecodeError) as error:
            raise click.ClickException(f"Could not load demo books: {error}") from error

        if not isinstance(seed_data, dict) or not isinstance(seed_data.get("books"), list):
            raise click.ClickException("Demo book data must contain a books list.")

        try:
            seeded_count = BookService(BookRepository()).seed_demo(seed_data["books"])
        except ValidationError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Added {seeded_count} demo books.")

    @app.cli.command("reset-user-password")
    @click.argument("email")
    def reset_user_password_command(email):
        """Reset a user's password when they cannot sign in."""
        user = AuthService(UserRepository()).find_email(email)
        if user is None:
            raise click.ClickException("No account matches that email.")
        password = click.prompt(
            "New password",
            hide_input=True,
            confirmation_prompt=True,
        )
        try:
            AuthService(UserRepository()).reset_password(
                user.user_id,
                password,
                password,
            )
        except ValidationError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Password reset for {user.username}.")

    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return str(error), 400

    @app.errorhandler(PermissionDenied)
    def handle_permission_error(error):
        return str(error), 403

    @app.errorhandler(NotFoundError)
    def handle_not_found_error(error):
        return str(error), 404

    return app