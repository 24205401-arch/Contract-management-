from flask import Flask
from pymongo import MongoClient

from config import Config
from .extensions import login_manager, oauth


def create_app(test_db=None):
    """
    test_db lets the test suite (and only the test suite) inject a
    mongomock database instead of connecting to real MongoDB.
    """
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_db is not None:
        app.db = test_db
    else:
        client = MongoClient(app.config["MONGO_URI"])
        app.db = client.get_default_database()

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    from .auth import auth_bp
    from .orders import orders_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(orders_bp)

    from .models import find_user_by_id, STATUS_LABELS, WORK_TYPE_LABELS

    @login_manager.user_loader
    def load_user(user_id):
        return find_user_by_id(user_id)

    @app.context_processor
    def inject_globals():
        return dict(status_labels=STATUS_LABELS, work_type_labels=WORK_TYPE_LABELS)

    from .commands import register_commands
    register_commands(app)

    return app
