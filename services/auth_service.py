"""
app/services/auth_service.py
-----------------------------
Business logic for user authentication:
  - register
  - login / logout
  - token refresh
  - password reset flow (email-less stub for now)
  - brute-force lockout
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token

from app import db, bcrypt
from app.models.user import User

logger = logging.getLogger(__name__)


class AuthService:
    """Stateless service; all methods are classmethods."""

    # ── Register ──────────────────────────────────────────────────────────────

    @classmethod
    def register(cls, data: dict) -> tuple[dict, int]:
        """
        Create a new user account.

        Args:
            data: Validated registration payload from the schema.

        Returns:
            (response_dict, http_status_code)
        """
        email = data["email"].lower().strip()

        # Duplicate check
        if User.query.filter_by(email=email).first():
            return {"success": False, "message": "An account with this email already exists."}, 409

        password_hash = bcrypt.generate_password_hash(data["password"]).decode("utf-8")

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=password_hash,
            first_name=data["first_name"].strip(),
            last_name=data["last_name"].strip(),
            date_of_birth=data.get("date_of_birth"),
            gender=data.get("gender"),
            phone_number=data.get("phone_number"),
        )

        db.session.add(user)
        db.session.commit()

        logger.info("New user registered: %s", email)

        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        return {
            "success": True,
            "message": "Account created successfully.",
            "user": user.to_dict(),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }, 201

    # ── Login ─────────────────────────────────────────────────────────────────

    @classmethod
    def login(cls, data: dict) -> tuple[dict, int]:
        """
        Authenticate a user and issue JWT tokens.

        Enforces brute-force lockout after MAX_LOGIN_ATTEMPTS failures.
        """
        email = data["email"].lower().strip()
        password = data["password"]

        user: User | None = User.query.filter_by(email=email).first()

        # Unknown email — return generic message to prevent user enumeration
        if not user:
            return {"success": False, "message": "Invalid email or password."}, 401

        # Account locked?
        if user.is_locked:
            remaining = int(
                (user.locked_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()
            )
            return {
                "success": False,
                "message": f"Account locked. Try again in {remaining // 60} min {remaining % 60} sec.",
            }, 403

        # Account suspended?
        if not user.is_active:
            return {"success": False, "message": "Account is suspended. Contact support."}, 403

        # Password check
        if not bcrypt.check_password_hash(user.password_hash, password):
            cls._record_failed_attempt(user)
            remaining = current_app.config["MAX_LOGIN_ATTEMPTS"] - user.login_attempts
            if remaining > 0:
                return {
                    "success": False,
                    "message": f"Invalid email or password. {remaining} attempt(s) remaining.",
                }, 401
            return {
                "success": False,
                "message": "Account locked due to too many failed attempts.",
            }, 403

        # ── Success ──────────────────────────────────────────────────────────
        cls._reset_failed_attempts(user)
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        access_token = create_access_token(identity=user.id)
        refresh_token = create_refresh_token(identity=user.id)

        logger.info("User logged in: %s", email)

        return {
            "success": True,
            "message": "Login successful.",
            "user": user.to_dict(),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }, 200

    # ── Token refresh ─────────────────────────────────────────────────────────

    @classmethod
    def refresh_token(cls, user_id: str) -> tuple[dict, int]:
        user = User.query.get(user_id)
        if not user or not user.is_active:
            return {"success": False, "message": "User not found or inactive."}, 401

        access_token = create_access_token(identity=user.id)
        return {"success": True, "access_token": access_token}, 200

    # ── Password reset (stub) ─────────────────────────────────────────────────

    @classmethod
    def request_password_reset(cls, email: str) -> tuple[dict, int]:
        """
        Initiates a password-reset flow.
        In production: generate a signed token and email it to the user.
        Here we return success regardless to prevent user enumeration.
        """
        user = User.query.filter_by(email=email.lower().strip()).first()
        if user:
            # TODO: generate token, send email
            logger.info("Password reset requested for: %s", email)
        return {
            "success": True,
            "message": "If that email exists, a reset link has been sent.",
        }, 200

    @classmethod
    def reset_password(cls, token: str, new_password: str) -> tuple[dict, int]:
        """Stub — validate signed reset token then update password."""
        # TODO: validate token, find user, update hash
        return {"success": False, "message": "Password reset not yet implemented."}, 501

    # ── Private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _record_failed_attempt(cls, user: User) -> None:
        max_attempts = current_app.config["MAX_LOGIN_ATTEMPTS"]
        lockout_secs = current_app.config["LOCKOUT_DURATION"]

        user.login_attempts += 1
        if user.login_attempts >= max_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(seconds=lockout_secs)
            logger.warning("Account locked: %s", user.email)
        db.session.commit()

    @classmethod
    def _reset_failed_attempts(cls, user: User) -> None:
        user.login_attempts = 0
        user.locked_until = None
        db.session.commit()
