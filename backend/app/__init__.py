import json
import os

import click
from flask import Flask

from .config import Config
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

    from .models import BookRecord, LoanRecord, Librarian, Patron, UserRecord
    from .routes.auth import auth_bp
    from .routes.books import books_bp
    from .routes.dashboard import dashboard_bp
    from .routes.landing import landing_bp
    from .routes.loans import loans_bp
    from .routes.members import members_bp
    from .routes.social import social_bp
    from .schema_migrations import upgrade_legacy_sqlite_schema
    from .services.auth_service import AuthService
    from .services.book_service import BookService
    from .repositories.book_repository import BookRepository
    from .repositories.user_repository import UserRepository

    with app.app_context():
        db.create_all()
        upgrade_legacy_sqlite_schema()

    app.register_blueprint(landing_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(social_bp)

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