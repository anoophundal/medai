"""
config/settings.py
------------------
Centralised configuration for all environments.
Values are loaded from environment variables (or .env via python-dotenv).
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class BaseConfig:
    """Shared settings across all environments."""

    # ── Core Flask ─────────────────────────────────────────────────────────
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-32chars!")
    APP_NAME: str = os.getenv("APP_NAME", "Healthcare Diagnosis Assistant")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")

    # ── Database ───────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, '..', 'healthcare.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # ── JWT ────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me!")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", 2592000))
    )
    JWT_TOKEN_LOCATION: list = ["headers"]
    JWT_HEADER_NAME: str = "Authorization"
    JWT_HEADER_TYPE: str = "Bearer"

    # ── Security ───────────────────────────────────────────────────────────
    BCRYPT_LOG_ROUNDS: int = int(os.getenv("BCRYPT_LOG_ROUNDS", 12))
    MAX_LOGIN_ATTEMPTS: int = int(os.getenv("MAX_LOGIN_ATTEMPTS", 5))
    LOCKOUT_DURATION: int = int(os.getenv("LOCKOUT_DURATION", 900))  # seconds

    # ── CORS ───────────────────────────────────────────────────────────────
    CORS_ORIGINS: list = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")

    # ── ML ─────────────────────────────────────────────────────────────────
    MODEL_DIR: str = os.getenv(
        "MODEL_DIR", os.path.join(BASE_DIR, "..", "app", "ml", "models")
    )
    MODEL_VERSION: str = os.getenv("MODEL_VERSION", "v1.0")


class DevelopmentConfig(BaseConfig):
    DEBUG: bool = True
    SQLALCHEMY_ECHO: bool = False   # set True to log all SQL


class ProductionConfig(BaseConfig):
    DEBUG: bool = False
    SQLALCHEMY_ECHO: bool = False
    # Override: force strong secrets in prod
    SECRET_KEY: str = os.environ["SECRET_KEY"]
    JWT_SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]


class TestingConfig(BaseConfig):
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(seconds=300)
    BCRYPT_LOG_ROUNDS: int = 4  # faster for tests


# ── Config map ─────────────────────────────────────────────────────────────
config_map: dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config() -> BaseConfig:
    env = os.getenv("FLASK_ENV", "development")
    return config_map.get(env, config_map["default"])
