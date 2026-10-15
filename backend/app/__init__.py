import os

from flask import Flask

from .config import Config
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

    from .models.user_record import UserRecord
    from .routes.auth import auth_bp

    with app.app_context():
        db.create_all()

    app.register_blueprint(auth_bp)
    return app