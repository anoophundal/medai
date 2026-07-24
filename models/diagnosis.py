"""
app/models/diagnosis.py
------------------------
DiagnosisResult — stores the ML output for a completed chat session.
"""

from datetime import datetime, timezone
from app import db


class DiagnosisResult(db.Model):
    """
    Persisted ML diagnosis for a chat session.

    predictions      : JSON list[dict] — [{disease, confidence, matched_symptoms, description}]
    risk_level       : 'low' | 'medium' | 'high'
    severity_score   : 0-100 composite score
    recommendations  : JSON list[str]
    disclaimer       : standard medical disclaimer text
    model_version    : which model artefact produced this result
    """

    __tablename__ = "diagnosis_results"

    # ── Identity ─────────────────────────────────────────────────────────────
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id = db.Column(
        db.String(36),
        db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )

    # ── Input ─────────────────────────────────────────────────────────────────
    symptoms_input = db.Column(db.Text, nullable=False)       # JSON list of symptom strings
    symptom_severity = db.Column(db.Text, nullable=True)      # JSON dict {symptom: severity_int}

    # ── Output ────────────────────────────────────────────────────────────────
    predictions = db.Column(db.Text, nullable=False)          # JSON list of prediction objects
    primary_disease = db.Column(db.String(200), nullable=True)
    primary_confidence = db.Column(db.Float, nullable=True)
    risk_level = db.Column(db.String(10), nullable=False)     # low | medium | high
    severity_score = db.Column(db.Float, nullable=False)      # 0–100
    recommendations = db.Column(db.Text, nullable=True)       # JSON list[str]
    disclaimer = db.Column(db.Text, nullable=True)

    # ── Meta ──────────────────────────────────────────────────────────────────
    model_version = db.Column(db.String(20), nullable=True)
    processing_time_ms = db.Column(db.Integer, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "symptoms_input": json.loads(self.symptoms_input) if self.symptoms_input else [],
            "symptom_severity": json.loads(self.symptom_severity) if self.symptom_severity else {},
            "predictions": json.loads(self.predictions) if self.predictions else [],
            "primary_disease": self.primary_disease,
            "primary_confidence": self.primary_confidence,
            "risk_level": self.risk_level,
            "severity_score": self.severity_score,
            "recommendations": json.loads(self.recommendations) if self.recommendations else [],
            "disclaimer": self.disclaimer,
            "model_version": self.model_version,
            "processing_time_ms": self.processing_time_ms,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<DiagnosisResult {self.id[:8]} disease={self.primary_disease}>"
