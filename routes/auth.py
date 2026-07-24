"""
app/routes/auth.py
-------------------
Authentication endpoints:
  POST /api/auth/register
  POST /api/auth/login
  POST /api/auth/refresh
  POST /api/auth/forgot-password
  POST /api/auth/reset-password
  GET  /api/auth/me
"""

import logging
from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.auth_service import AuthService
from app.utils.helpers import validate_json, success_response, error_response
from app.utils.schemas import (
    RegisterSchema, LoginSchema, ForgotPasswordSchema, ResetPasswordSchema
)

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
@validate_json(RegisterSchema)
def register(data):
    """
    Create a new user account.

    Body:
        first_name, last_name, email, password, [gender, date_of_birth, phone_number]

    Returns:
        201 + user object + JWT tokens
    """
    result, status = AuthService.register(data)
    return (success_response(result, result.get("message", "Registered."), status)
            if result["success"] else error_response(result["message"], status))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
@validate_json(LoginSchema)
def login(data):
    """
    Authenticate a user and issue JWT tokens.

    Body:
        email, password

    Returns:
        200 + user object + JWT tokens
    """
    result, status = AuthService.login(data)
    return (success_response(result, result.get("message", "Logged in."), status)
            if result["success"] else error_response(result["message"], status))


# ── Token refresh ─────────────────────────────────────────────────────────────

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """
    Issue a new access token from a valid refresh token.

    Headers:
        Authorization: Bearer <refresh_token>

    Returns:
        200 + new access_token
    """
    user_id = get_jwt_identity()
    result, status = AuthService.refresh_token(user_id)
    return (success_response(result, "Token refreshed.", status)
            if result["success"] else error_response(result["message"], status))


# ── Forgot password ───────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["POST"])
@validate_json(ForgotPasswordSchema)
def forgot_password(data):
    """
    Trigger password-reset email flow.

    Body:
        email
    """
    result, status = AuthService.request_password_reset(data["email"])
    return success_response(message=result["message"]), status


# ── Reset password ────────────────────────────────────────────────────────────

@auth_bp.route("/reset-password", methods=["POST"])
@validate_json(ResetPasswordSchema)
def reset_password(data):
    """
    Complete the password reset using a signed token.

    Body:
        token, new_password
    """
    result, status = AuthService.reset_password(data["token"], data["new_password"])
    return (success_response(message=result["message"])
            if result["success"] else error_response(result["message"], status))


# ── Get current user ──────────────────────────────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """
    Return the authenticated user's profile.

    Headers:
        Authorization: Bearer <access_token>
    """
    from app.models.user import User
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return error_response("User not found.", 404)
    return success_response(user.to_dict(), "User fetched.")
