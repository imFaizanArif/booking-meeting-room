from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .errors import register_error_handlers
from .extensions import get_session_factory


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(
        app,
        origins=Config.CORS_ORIGINS,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        supports_credentials=True,
    )

    register_error_handlers(app)

    from .routes.bookings import bookings_bp
    from .routes.rooms import rooms_bp
    from .routes.users import users_bp
    from .routes.analytics import analytics_bp

    app.register_blueprint(rooms_bp, url_prefix="/api/rooms")
    app.register_blueprint(bookings_bp, url_prefix="/api/bookings")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "service": "kodifly-meeting-room-api"})

    @app.teardown_appcontext
    def remove_session(exception=None):
        get_session_factory().remove()

    return app
