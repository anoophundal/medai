"""
app/services/chat_service.py
-----------------------------
Business logic for the conversational chat interface:
  - create / retrieve / archive sessions
  - persist messages
  - generate AI assistant replies (calls ML service)
  - extract and accumulate symptoms across a session
"""

import uuid
import json
import logging
from datetime import datetime, timezone

from app import db
from app.models.chat import ChatSession, ChatMessage
from app.models.symptom import SymptomRecord

logger = logging.getLogger(__name__)

# ── Conversation-stage constants ─────────────────────────────────────────────
STAGE_GREETING = "greeting"
STAGE_SYMPTOM_COLLECTION = "symptom_collection"
STAGE_DETAIL_GATHERING = "detail_gathering"
STAGE_READY_TO_DIAGNOSE = "ready_to_diagnose"
STAGE_DIAGNOSIS_SHOWN = "diagnosis_shown"


class ChatService:

    # ── Session management ────────────────────────────────────────────────────

    @classmethod
    def create_session(cls, user_id: str) -> dict:
        """Start a new chat session and send the greeting message."""
        session_id = str(uuid.uuid4())

        session = ChatSession(
            id=session_id,
            user_id=user_id,
            title="New Consultation",
            status="active",
            extracted_symptoms=json.dumps([]),
        )
        db.session.add(session)
        db.session.flush()

        # Greeting message from assistant
        greeting = (
            "Hello! I'm your AI Health Assistant. 👋\n\n"
            "I'm here to help you understand your symptoms and provide "
            "general health guidance.\n\n"
            "**Please describe what you're feeling today.** "
            "For example:\n"
            "• *\"I have a headache and fever since yesterday\"*\n"
            "• *\"I feel nauseous and have stomach pain\"*\n\n"
            "⚠️ *This is not a substitute for professional medical advice. "
            "Always consult a qualified healthcare provider for diagnosis and treatment.*"
        )
        cls._save_message(session_id, "assistant", greeting, "greeting")
        db.session.commit()

        logger.info("New chat session created: %s for user: %s", session_id, user_id)
        return session.to_dict(include_messages=True)

    @classmethod
    def get_session(cls, session_id: str, user_id: str) -> dict | None:
        session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
        return session.to_dict(include_messages=True) if session else None

    @classmethod
    def list_sessions(cls, user_id: str) -> list[dict]:
        sessions = (
            ChatSession.query.filter_by(user_id=user_id)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )
        return [s.to_dict() for s in sessions]

    @classmethod
    def archive_session(cls, session_id: str, user_id: str) -> bool:
        session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
        if not session:
            return False
        session.status = "archived"
        db.session.commit()
        return True

    # ── Message processing ────────────────────────────────────────────────────

    @classmethod
    def process_message(cls, session_id: str, user_id: str, user_text: str) -> dict:
        """
        Accept a user message, persist it, generate an AI reply,
        extract symptoms, and return the full updated session.
        """
        session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
        if not session:
            return {"success": False, "message": "Session not found."}, 404

        if session.status != "active":
            return {
                "success": False,
                "message": "This session is no longer active.",
            }, 400

        # Save user message
        cls._save_message(session_id, "user", user_text.strip())

        # Auto-title the session from the first user message
        if session.title == "New Consultation":
            session.title = cls._generate_title(user_text)

        # ── Generate AI response ──────────────────────────────────────────────
        from app.services.ml_service import MLService

        current_symptoms = json.loads(session.extracted_symptoms or "[]")
        new_symptoms = MLService.extract_symptoms(user_text)

        # Merge & deduplicate
        all_symptoms = list(set(current_symptoms + new_symptoms))
        session.extracted_symptoms = json.dumps(all_symptoms)

        # Save symptom records
        cls._persist_symptoms(new_symptoms, session_id, user_id)

        # Decide reply based on conversation state
        reply_text, reply_type = cls._generate_reply(
            user_text, all_symptoms, session
        )

        msg = cls._save_message(session_id, "assistant", reply_text, reply_type)
        session.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return {
            "success": True,
            "message": msg.to_dict(),
            "session": session.to_dict(),
            "extracted_symptoms": all_symptoms,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    @classmethod
    def _generate_reply(
        cls, user_text: str, symptoms: list[str], session: ChatSession
    ) -> tuple[str, str]:
        """
        Decide what the assistant should say next.
        Returns (reply_text, message_type).
        """
        lowered = user_text.lower()

        # Check if user wants a diagnosis
        diagnosis_triggers = [
            "diagnose", "what do i have", "analyze", "check my symptoms",
            "what's wrong", "whats wrong", "tell me what", "give me results",
            "run diagnosis",
        ]
        wants_diagnosis = any(t in lowered for t in diagnosis_triggers)

        if wants_diagnosis and symptoms:
            return cls._ready_to_diagnose_reply(symptoms), "diagnosis_prompt"

        if len(symptoms) == 0:
            return (
                "I didn't catch any specific symptoms in your message. "
                "Could you describe what you're experiencing? "
                "For example: *fever, headache, cough, fatigue, nausea, chest pain…*",
                "text",
            )

        if len(symptoms) < 3:
            return cls._follow_up_reply(symptoms), "text"

        return cls._sufficient_symptoms_reply(symptoms), "text"

    @classmethod
    def _follow_up_reply(cls, symptoms: list[str]) -> str:
        symptom_list = ", ".join(f"**{s}**" for s in symptoms)
        return (
            f"I've noted the following symptoms: {symptom_list}.\n\n"
            "To give you a more accurate assessment, could you also tell me:\n"
            "• How long have you had these symptoms?\n"
            "• Are you experiencing any fever, chills, or fatigue?\n"
            "• Do you have any chest pain or difficulty breathing?\n"
            "• Any nausea, vomiting, or digestive issues?"
        )

    @classmethod
    def _sufficient_symptoms_reply(cls, symptoms: list[str]) -> str:
        symptom_list = ", ".join(f"**{s}**" for s in symptoms)
        return (
            f"Thank you for sharing. I've recorded these symptoms: {symptom_list}.\n\n"
            "I have enough information to run an initial assessment. "
            "Type **'diagnose'** whenever you're ready, or continue describing "
            "any additional symptoms."
        )

    @classmethod
    def _ready_to_diagnose_reply(cls, symptoms: list[str]) -> str:
        symptom_list = ", ".join(f"**{s}**" for s in symptoms)
        return (
            f"Running analysis on your symptoms: {symptom_list}.\n\n"
            "🔬 Processing with our diagnostic AI… "
            "Your results will appear in the **Diagnosis** tab momentarily.\n\n"
            "⚠️ *Remember: This is an AI-generated estimate for informational "
            "purposes only. Please consult a licensed physician for medical advice.*"
        )

    @classmethod
    def _save_message(
        cls,
        session_id: str,
        sender: str,
        content: str,
        message_type: str = "text",
        metadata: dict | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            sender=sender,
            content=content,
            message_type=message_type,
            extra_data=json.dumps(metadata) if metadata else None,
        )
        db.session.add(msg)
        return msg

    @classmethod
    def _persist_symptoms(
        cls, symptoms: list[str], session_id: str, user_id: str
    ) -> None:
        for name in symptoms:
            record = SymptomRecord(
                id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                symptom_name=name,
            )
            db.session.add(record)

    @staticmethod
    def _generate_title(text: str) -> str:
        words = text.split()[:6]
        title = " ".join(words)
        return title[:80] + ("…" if len(text) > 80 else "")
