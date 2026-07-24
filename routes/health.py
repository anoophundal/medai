"""
app/routes/health.py
---------------------
System health check endpoint — used by load balancers and uptime monitors.
  GET /api/health
  GET /api/health/db
"""

import logging
from flask import Blueprint, jsonify, current_app

logger = logging.getLogger(__name__)
health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Basic liveness probe."""
    return jsonify({
        "status": "healthy",
        "app": current_app.config.get("APP_NAME"),
        "version": current_app.config.get("APP_VERSION"),
    }), 200


@health_bp.route("/health/db", methods=["GET"])
def db_health():
    """Database connectivity check."""
    from app import db
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        logger.error("DB health check failed: %s", e)
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 503
