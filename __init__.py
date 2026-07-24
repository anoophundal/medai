"""
app/__init__.py
---------------
Application factory.  Creates and configures the Flask app,
registers extensions, blueprints, and error handlers.
"""

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS

from config.settings import get_config

# ── Extension singletons ────────────────────────────────────────────────────
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
bcrypt = Bcrypt()


def create_app(config_class=None) -> Flask:
    """
    Flask application factory.

    Args:
        config_class: Optional config object; falls back to FLASK_ENV setting.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)

    # ── Configuration ───────────────────────────────────────────────────────
    cfg = config_class or get_config()
    app.config.from_object(cfg)

    # ── Extensions ──────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    bcrypt.init_app(app)

    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )

    # ── JWT callbacks ────────────────────────────────────────────────────────
    _register_jwt_callbacks(jwt)

    # ── Blueprints ───────────────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.chat import chat_bp
    from app.routes.diagnosis import diagnosis_bp
    from app.routes.profile import profile_bp
    from app.routes.health import health_bp

    app.register_blueprint(auth_bp,      url_prefix="/api/auth")
    app.register_blueprint(chat_bp,      url_prefix="/api/chat")
    app.register_blueprint(diagnosis_bp, url_prefix="/api/diagnosis")
    app.register_blueprint(profile_bp,   url_prefix="/api/profile")
    app.register_blueprint(health_bp,    url_prefix="/api")

    # ── Global error handlers ────────────────────────────────────────────────
    _register_error_handlers(app)

    # ── Shell context ────────────────────────────────────────────────────────
    @app.shell_context_processor
    def shell_context():
        from app.models.user import User
        from app.models.chat import ChatSession, ChatMessage
        from app.models.diagnosis import DiagnosisResult
        from app.models.symptom import SymptomRecord
        return dict(db=db, User=User, ChatSession=ChatSession,
                    ChatMessage=ChatMessage, DiagnosisResult=DiagnosisResult,
                    SymptomRecord=SymptomRecord)

    return app


# ── Private helpers ──────────────────────────────────────────────────────────

def _register_jwt_callbacks(jwt_manager: JWTManager) -> None:
    """Customise JWT error responses."""

    @jwt_manager.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"success": False, "message": "Token has expired."}), 401

    @jwt_manager.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({"success": False, "message": "Invalid token."}), 401

    @jwt_manager.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({"success": False, "message": "Authorization token required."}), 401

    @jwt_manager.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({"success": False, "message": "Token has been revoked."}), 401


def _register_error_handlers(app: Flask) -> None:
    """Register global HTTP error handlers."""

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"success": False, "message": "Bad request.", "error": str(e)}), 400

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"success": False, "message": "Forbidden."}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "message": "Resource not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"success": False, "message": "Method not allowed."}), 405

    @app.errorhandler(422)
    def unprocessable(e):
        return jsonify({"success": False, "message": "Unprocessable entity.", "error": str(e)}), 422

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"success": False, "message": "Too many requests. Please slow down."}), 429

    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error(f"Internal server error: {e}")
        return jsonify({"success": False, "message": "Internal server error."}), 500
