import os

from flask import Flask

from .config import Config
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

    from .models import BookRecord, LoanRecord, Librarian, Patron, UserRecord
    from .routes.auth import auth_bp
    from .routes.books import books_bp
    from .routes.dashboard import dashboard_bp
    from .routes.landing import landing_bp
    from .routes.loans import loans_bp
    from .routes.members import members_bp
    from .schema_migrations import upgrade_legacy_sqlite_schema

    with app.app_context():
        db.create_all()
        upgrade_legacy_sqlite_schema()

    app.register_blueprint(landing_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(loans_bp)
    app.register_blueprint(members_bp)

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