import json
import os
import shutil
from datetime import date
from urllib.parse import urlsplit

import click
from flask import Flask, render_template, request, session, url_for

from .config import COVER_COLORS, Config
from .constants import UNCATEGORIZED, UNCATEGORIZED_SLUG
from .csrf import CSRFProtect
from .exceptions import NotFoundError, PermissionDenied, ValidationError
from .extensions import db, migrate


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
    migrate.init_app(
        app,
        db,
        directory=os.path.join(project_root, "backend", "migrations"),
    )
    CSRFProtect().init_app(app)

    from . import models
    from .routes.auth import auth_bp
    from .routes.books import books_bp
    from .routes.dashboard import dashboard_bp
    from .routes.genres import genres_bp
    from .routes.fees import fees_bp
    from .routes.landing import landing_bp
    from .routes.loans import loans_bp
    from .routes.members import members_bp
    from .routes.notifications import notifications_bp
    from .routes.patron import patron_bp
    from .routes.reservations import reservations_bp
    from .routes.social import social_bp
    from .schema_migrations import upgrade_legacy_sqlite_schema
    from .services.auth_service import AuthService
    from .services.backup_service import BackupService
    from .services.book_service import BookService
    from .services.catalog_seed_service import CatalogSeedService
    from .repositories.book_repository import BookRepository
    from .repositories.basket_repository import BasketRepository
    from .repositories.favorite_repository import FavoriteRepository
    from .repositories.genre_repository import GenreRepository
    from .repositories.user_repository import UserRepository

    initialize_from_starter_database = (
        not test_config
        and app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///bookend.db"
        and not os.path.exists(os.path.join(app.instance_path, "bookend.db"))
    )

    if initialize_from_starter_database:
        starter_database_path = os.path.join(
            os.path.dirname(__file__),
            "bookend-starter.sqlite",
        )
        shutil.copyfile(
            starter_database_path,
            os.path.join(app.instance_path, "bookend.db"),
        )

    with app.app_context():
        if app.config.get("TESTING"):
            db.create_all()
        upgrade_legacy_sqlite_schema()

    app.register_blueprint(landing_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(genres_bp)
    app.register_blueprint(fees_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(patron_bp)
    app.register_blueprint(reservations_bp)

    @app.before_request
    def confirm_destructive_post():
        confirmation_endpoints = {
            "books.delete",
            "books.delete_selected",
            "genres.remove",
            "social.delete_review",
            "social.delete_review_as_librarian",
            "patron.basket_remove",
            "dashboard.import_backup",
        }
        if (
            request.method != "POST"
            or request.endpoint not in confirmation_endpoints
            or request.form.get("confirm_action") == "confirmed"
        ):
            return None
        librarian_endpoints = {
            "books.delete",
            "books.delete_selected",
            "genres.remove",
            "social.delete_review_as_librarian",
            "dashboard.import_backup",
        }
        if (
            request.endpoint in librarian_endpoints
            and session.get("role") != "librarian"
        ):
            return None

        title = request.form.get("_confirm_title", "Confirm this action")
        message = request.form.get(
            "_confirm_message",
            "Please review this action before continuing.",
        )
        note = request.form.get("_confirm_note", "")
        action = request.form.get("_confirm_action", "Confirm")
        requires_delete_phrase = request.endpoint == "books.delete_selected"
        requires_backup_file = request.endpoint == "dashboard.import_backup"

        if request.endpoint == "books.delete_selected":
            selected_ids = request.form.getlist("ids[]")
            titles = []
            for value in selected_ids:
                try:
                    book_id = int(value)
                except (TypeError, ValueError):
                    continue
                book_record = db.session.get(models.BookRecord, book_id)
                if book_record is not None:
                    titles.append(book_record.title)
            title = "Delete selected books permanently?"
            count = len(selected_ids)
            message = (
                f"{count} book{'s' if count != 1 else ''} selected: "
                f"{', '.join(titles[:5])}"
            )
            if len(titles) > 5:
                message += f", and {len(titles) - 5} more"
            message += ". Loan history is kept; favorites and reviews are removed."
            note = "This cannot be undone."
            action = "Delete selected"

        parsed_referrer = urlsplit(request.referrer or "")
        cancel_url = (
            f"{parsed_referrer.path}?{parsed_referrer.query}"
            if parsed_referrer.netloc in {"", request.host}
            and parsed_referrer.path.startswith("/")
            and not parsed_referrer.path.startswith("//")
            else url_for("landing.index")
        )
        form_values = [
            (key, value)
            for key, value in request.form.items(multi=True)
            if key not in {
                "csrf_token",
                "confirm_action",
                "confirm_text",
                "_confirm_title",
                "_confirm_message",
                "_confirm_note",
                "_confirm_action",
            }
        ]
        return render_template(
            "confirm_action.html",
            confirm_title=title,
            confirm_message=message,
            confirm_note=note,
            confirm_action=action,
            csrf_token_value=request.form.get("csrf_token", ""),
            form_values=form_values,
            requires_delete_phrase=requires_delete_phrase,
            requires_backup_file=requires_backup_file,
            cancel_url=cancel_url,
        )

    @app.template_filter("peso")
    def format_peso(amount):
        return f"₱{amount:,.2f}"

    @app.context_processor
    def library_navigation_context():
        from .routes.auth import _signed_in_user
        from .repositories.book_repository import BookRepository
        from .repositories.loan_repository import LoanRepository
        from .repositories.notification_repository import NotificationRepository
        from .repositories.reservation_repository import ReservationRepository
        from .services.notification_service import NotificationService

        current_user = _signed_in_user()
        favorite_ids = set()
        favorite_count = 0
        basket_count = 0
        overdue_count = 0
        fee_member_count = 0
        notification_count = 0
        ready_reservation_count = 0
        active_book_ids = set()
        if current_user is not None and current_user.is_patron():
            favorite_ids = set(
                FavoriteRepository().book_ids_for_user(current_user.user_id)
            )
            favorite_count = len(favorite_ids)
            basket_repository = BasketRepository()
            basket_ids = basket_repository.book_ids_for_user(current_user.user_id)
            if not basket_ids:
                legacy_ids = session.get("basket_book_ids", [])
                if isinstance(legacy_ids, list):
                    basket_ids = [
                        book_id for book_id in legacy_ids
                        if BookRepository().find_book(book_id) is not None
                    ]
            basket_count = len(set(basket_ids))
            loan_repository = LoanRepository()
            active_book_ids = loan_repository.active_book_ids(current_user.user_id)
            notification_repository = NotificationRepository()
            notification_service = NotificationService(
                notification_repository,
                loan_repository,
                BookRepository(),
            )
            notification_service.sync_due_date_reminders(current_user.user_id)
            ready_reservation_count = (
                ReservationRepository().count_ready_for_patron(
                    current_user.user_id
                )
            )
            notification_count = notification_repository.unread_count(
                current_user.user_id
            )
        elif current_user is not None and current_user.is_librarian():
            from .repositories.fee_repository import FeeRepository

            fee_member_count = FeeRepository().members_with_outstanding_count()
            loan_repository = LoanRepository()
            overdue = loan_repository.find_overdue()
            overdue_count = len(overdue)
            notification_repository = NotificationRepository()
            NotificationService(
                notification_repository,
                loan_repository,
                BookRepository(),
            ).sync_overdue_notifications()

            notification_count = notification_repository.unread_count(
                current_user.user_id
            )
        return {
            "current_user": current_user,
            "favorite_ids": favorite_ids,
            "favorite_count": favorite_count,
            "basket_count": basket_count,
            "overdue_count": overdue_count,
            "fee_member_count": fee_member_count,
            "notification_count": notification_count,
            "ready_reservation_count": ready_reservation_count,
            "active_book_ids": active_book_ids,
            "navigation_genres": GenreRepository().list_genres(),
            "uncategorized_count": BookRepository().uncategorized_count(),
            "archived_book_count": BookRepository().archived_count(),
            "UNCATEGORIZED": UNCATEGORIZED,
            "UNCATEGORIZED_SLUG": UNCATEGORIZED_SLUG,
            "cover_colors": COVER_COLORS,
            "site_year": date.today().year,
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

    @app.cli.command("seed-catalog")
    def seed_catalog_command():
        """Copy local SQLite books and genres into the configured database."""
        source_path = os.path.join(app.instance_path, "bookend.db")
        if not os.path.isfile(source_path):
            source_path = os.path.join(
                os.path.dirname(__file__),
                "bookend-starter.sqlite",
            )
        try:
            row_counts = CatalogSeedService().seed_from_sqlite(source_path)
        except (OSError, ValueError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(
            "Seeded "
            f"{row_counts['books']} books and "
            f"{row_counts['genres']} genres from {source_path}."
        )

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