"""
app/routes/diagnosis.py
------------------------
Diagnosis prediction endpoints:
  POST  /api/diagnosis/predict          — run ML prediction on symptoms
  GET   /api/diagnosis/history          — list past diagnoses for user
  GET   /api/diagnosis/<id>             — get a specific diagnosis result
  GET   /api/diagnosis/symptoms/list    — return supported symptom vocabulary
"""

import uuid
import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app import db
from app.models.diagnosis import DiagnosisResult
from app.models.user import User
from app.services.ml_service import MLService, SYMPTOM_VOCABULARY
from app.utils.helpers import success_response, error_response, validate_json
from app.utils.schemas import DiagnoseSchema

logger = logging.getLogger(__name__)
diagnosis_bp = Blueprint("diagnosis", __name__)


# ── Predict ───────────────────────────────────────────────────────────────────

@diagnosis_bp.route("/predict", methods=["POST"])
@jwt_required()
@validate_json(DiagnoseSchema)
def predict(data):
    """
    Run the ML diagnosis pipeline on a list of symptoms.

    Body:
        symptoms     — list of symptom strings (canonical or natural language)
        session_id   — optional session UUID to link result
        severity_map — optional {symptom: 1-10} severity scores

    Returns:
        201 + full DiagnosisResult object
    """
    user_id = get_jwt_identity()
    user: User | None = User.query.get(user_id)

    raw_symptoms: list[str] = data["symptoms"]
    session_id: str | None = data.get("session_id")
    severity_map: dict = data.get("severity_map", {})

    # Normalise: extract from free-text tokens if needed
    extracted: list[str] = []
    for s in raw_symptoms:
        if s in SYMPTOM_VOCABULARY:
            extracted.append(s)
        else:
            # Try NLP extraction on the token
            extracted.extend(MLService.extract_symptoms(s))

    # Deduplicate
    symptoms = list(set(extracted))

    if not symptoms:
        return error_response(
            "No recognisable symptoms found. "
            "Please describe your symptoms in more detail.", 422
        )

    # Run ML pipeline
    prediction = MLService.predict(
        symptoms=symptoms,
        user_age=user.age or 30 if user else 30,
        user_gender=user.gender or "unknown" if user else "unknown",
    )

    # Persist result
    result = DiagnosisResult(
        id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        symptoms_input=json.dumps(symptoms),
        symptom_severity=json.dumps(severity_map),
        predictions=json.dumps(prediction["predictions"]),
        primary_disease=prediction["primary_disease"],
        primary_confidence=prediction["primary_confidence"],
        risk_level=prediction["risk_level"],
        severity_score=prediction["severity_score"],
        recommendations=json.dumps(prediction["recommendations"]),
        disclaimer=prediction["disclaimer"],
        model_version=prediction["model_version"],
        processing_time_ms=prediction["processing_time_ms"],
    )
    db.session.add(result)
    db.session.commit()

    logger.info(
        "Diagnosis saved: %s | user=%s | disease=%s | risk=%s",
        result.id[:8], user_id[:8], prediction["primary_disease"], prediction["risk_level"],
    )

    return success_response(result.to_dict(), "Diagnosis completed.", 201)


# ── History ───────────────────────────────────────────────────────────────────

@diagnosis_bp.route("/history", methods=["GET"])
@jwt_required()
def history():
    """
    Return paginated diagnosis history for the authenticated user.

    Query params:
        page     — default 1
        per_page — default 10, max 50
    """
    user_id = get_jwt_identity()
    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 10)), 50)

    query = (
        DiagnosisResult.query
        .filter_by(user_id=user_id)
        .order_by(DiagnosisResult.created_at.desc())
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return success_response(
        {
            "results": [r.to_dict() for r in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
            "per_page": pagination.per_page,
        },
        "Diagnosis history fetched.",
    )


# ── Single result ─────────────────────────────────────────────────────────────

@diagnosis_bp.route("/<string:result_id>", methods=["GET"])
@jwt_required()
def get_result(result_id):
    """
    Retrieve a single diagnosis result by ID.

    Path:
        result_id — UUID of the DiagnosisResult
    """
    user_id = get_jwt_identity()
    result = DiagnosisResult.query.filter_by(id=result_id, user_id=user_id).first()
    if not result:
        return error_response("Diagnosis result not found.", 404)
    return success_response(result.to_dict(), "Result fetched.")


# ── Symptom vocabulary ────────────────────────────────────────────────────────

@diagnosis_bp.route("/symptoms/list", methods=["GET"])
@jwt_required()
def symptom_list():
    """
    Return the full list of supported symptom identifiers.
    Useful for the frontend symptom-picker component.
    """
    readable = [s.replace("_", " ").title() for s in SYMPTOM_VOCABULARY]
    payload = [
        {"id": sym, "label": label}
        for sym, label in zip(SYMPTOM_VOCABULARY, readable)
    ]
    return success_response(payload, f"{len(payload)} symptoms available.")
