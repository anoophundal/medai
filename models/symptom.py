"""
app/models/symptom.py
----------------------
SymptomRecord — tracks individual symptom entries for analytics
and ML feature building.
"""

from datetime import datetime, timezone
from app import db


class SymptomRecord(db.Model):
    """
    Granular symptom log entry.

    Each record captures a single symptom reported by the user in a
    session.  Aggregating records gives the feature vector fed to the
    ML pipeline.

    severity   : 1 (mild) – 10 (severe)
    duration   : duration in hours
    body_part  : optional anatomical location (e.g. 'chest', 'head')
    """

    __tablename__ = "symptom_records"

    # ── Identity ─────────────────────────────────────────────────────────────
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id = db.Column(
        db.String(36),
        db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ── Symptom data ──────────────────────────────────────────────────────────
    symptom_name = db.Column(db.String(200), nullable=False)
    severity = db.Column(db.Integer, nullable=True)       # 1–10 scale
    duration_hours = db.Column(db.Float, nullable=True)
    body_part = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    reported_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "symptom_name": self.symptom_name,
            "severity": self.severity,
            "duration_hours": self.duration_hours,
            "body_part": self.body_part,
            "notes": self.notes,
            "reported_at": self.reported_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<SymptomRecord {self.symptom_name} sev={self.severity}>"
