"""
app/routes/profile.py
----------------------
User profile management endpoints:
  GET    /api/profile            — get full profile
  PUT    /api/profile            — update profile fields
  POST   /api/profile/password   — change password
  GET    /api/profile/symptoms   — list symptom history
  GET    /api/profile/stats      — dashboard statistics
"""

import logging
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db, bcrypt
from app.models.user import User
from app.models.symptom import SymptomRecord
from app.models.diagnosis import DiagnosisResult
from app.models.chat import ChatSession
from app.utils.helpers import success_response, error_response, validate_json
from app.utils.schemas import UpdateProfileSchema, ChangePasswordSchema

logger = logging.getLogger(__name__)
profile_bp = Blueprint("profile", __name__)


# ── Get profile ───────────────────────────────────────────────────────────────

@profile_bp.route("", methods=["GET"])
@jwt_required()
def get_profile():
    """Return the full user profile."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return error_response("User not found.", 404)
    return success_response(user.to_dict(), "Profile fetched.")


# ── Update profile ────────────────────────────────────────────────────────────

@profile_bp.route("", methods=["PUT"])
@jwt_required()
@validate_json(UpdateProfileSchema)
def update_profile(data):
    """
    Update one or more profile fields.

    Body (all optional):
        first_name, last_name, date_of_birth, gender, blood_group,
        allergies, medical_history, phone_number
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return error_response("User not found.", 404)

    # Apply only provided fields
    for field, value in data.items():
        if hasattr(user, field):
            setattr(user, field, value)

    db.session.commit()
    logger.info("Profile updated: %s", user_id[:8])
    return success_response(user.to_dict(), "Profile updated.")


# ── Change password ───────────────────────────────────────────────────────────

@profile_bp.route("/password", methods=["POST"])
@jwt_required()
@validate_json(ChangePasswordSchema)
def change_password(data):
    """
    Change the authenticated user's password.

    Body:
        current_password, new_password
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return error_response("User not found.", 404)

    if not bcrypt.check_password_hash(user.password_hash, data["current_password"]):
        return error_response("Current password is incorrect.", 400)

    user.password_hash = bcrypt.generate_password_hash(data["new_password"]).decode("utf-8")
    db.session.commit()
    logger.info("Password changed: %s", user_id[:8])
    return success_response(message="Password updated successfully.")


# ── Symptom history ───────────────────────────────────────────────────────────

@profile_bp.route("/symptoms", methods=["GET"])
@jwt_required()
def symptom_history():
    """
    Return paginated symptom records for the user.

    Query params:
        page, per_page, session_id (optional)
    """
    user_id = get_jwt_identity()
    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 20)), 100)
    session_id = request.args.get("session_id")

    query = SymptomRecord.query.filter_by(user_id=user_id)
    if session_id:
        query = query.filter_by(session_id=session_id)
    query = query.order_by(SymptomRecord.reported_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return success_response(
        {
            "symptoms": [r.to_dict() for r in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        },
        "Symptom history fetched.",
    )


# ── Dashboard stats ───────────────────────────────────────────────────────────

@profile_bp.route("/stats", methods=["GET"])
@jwt_required()
def dashboard_stats():
    """
    Aggregate statistics for the user dashboard.

    Returns:
        total_sessions, total_diagnoses, most_common_symptoms,
        risk_breakdown, recent_diagnoses
    """
    user_id = get_jwt_identity()

    total_sessions = ChatSession.query.filter_by(user_id=user_id).count()
    total_diagnoses = DiagnosisResult.query.filter_by(user_id=user_id).count()

    # Risk breakdown
    results = DiagnosisResult.query.filter_by(user_id=user_id).all()
    risk_breakdown = {"low": 0, "medium": 0, "high": 0}
    for r in results:
        risk_breakdown[r.risk_level] = risk_breakdown.get(r.risk_level, 0) + 1

    # Most common symptoms (top 10)
    import json
    from collections import Counter
    symptom_counter: Counter = Counter()
    for r in results:
        try:
            syms = json.loads(r.symptoms_input)
            symptom_counter.update(syms)
        except Exception:
            pass
    top_symptoms = [
        {"symptom": k.replace("_", " ").title(), "count": v}
        for k, v in symptom_counter.most_common(10)
    ]

    # Recent diagnoses
    recent = (
        DiagnosisResult.query.filter_by(user_id=user_id)
        .order_by(DiagnosisResult.created_at.desc())
        .limit(5)
        .all()
    )

    return success_response(
        {
            "total_sessions": total_sessions,
            "total_diagnoses": total_diagnoses,
            "risk_breakdown": risk_breakdown,
            "top_symptoms": top_symptoms,
            "recent_diagnoses": [r.to_dict() for r in recent],
        },
        "Stats fetched.",
    )
