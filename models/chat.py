"""
app/models/chat.py
------------------
ChatSession  — one conversation thread per user.
ChatMessage  — individual message within a session.
"""

from datetime import datetime, timezone
from app import db


class ChatSession(db.Model):
    """
    A conversation thread between a user and the AI assistant.

    Each session tracks the full dialogue and accumulates a running
    list of extracted symptoms as the conversation progresses.
    """

    __tablename__ = "chat_sessions"

    # ── Identity ─────────────────────────────────────────────────────────────
    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    title = db.Column(db.String(200), nullable=True)          # auto-generated from first message
    status = db.Column(db.String(20), default="active")       # active | completed | archived
    extracted_symptoms = db.Column(db.Text, nullable=True)    # JSON list of symptom strings
    session_summary = db.Column(db.Text, nullable=True)       # brief AI-generated summary

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    messages = db.relationship(
        "ChatMessage",
        backref="session",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )
    diagnosis_result = db.relationship(
        "DiagnosisResult",
        backref="chat_session",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self, include_messages: bool = False) -> dict:
        import json
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "status": self.status,
            "extracted_symptoms": json.loads(self.extracted_symptoms) if self.extracted_symptoms else [],
            "session_summary": self.session_summary,
            "message_count": self.messages.count(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_messages:
            data["messages"] = [m.to_dict() for m in self.messages]
        return data

    def __repr__(self) -> str:
        return f"<ChatSession {self.id[:8]} user={self.user_id[:8]}>"


class ChatMessage(db.Model):
    """
    A single message within a ChatSession.

    sender  : 'user' | 'assistant'
    content : raw message text
    metadata: JSON blob — AI confidence, detected symptoms, etc.
    """

    __tablename__ = "chat_messages"

    # ── Identity ─────────────────────────────────────────────────────────────
    id = db.Column(db.String(36), primary_key=True)
    session_id = db.Column(
        db.String(36),
        db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Content ───────────────────────────────────────────────────────────────
    sender = db.Column(db.String(20), nullable=False)          # 'user' | 'assistant'
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(30), default="text")   # text | symptom_form | diagnosis
    extra_data = db.Column(db.Text, nullable=True)             # JSON blob

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "session_id": self.session_id,
            "sender": self.sender,
            "content": self.content,
            "message_type": self.message_type,
            "extra_data": json.loads(self.extra_data) if self.extra_data else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<ChatMessage {self.id[:8]} sender={self.sender}>"
