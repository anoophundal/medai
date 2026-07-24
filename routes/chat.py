"""
app/routes/chat.py
-------------------
Chat session & messaging endpoints:
  POST   /api/chat/sessions            — create new session
  GET    /api/chat/sessions            — list user sessions
  GET    /api/chat/sessions/<id>       — get session + messages
  DELETE /api/chat/sessions/<id>       — archive session
  POST   /api/chat/message             — send message & get AI reply
"""

import logging
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.chat_service import ChatService
from app.utils.helpers import success_response, error_response, validate_json
from app.utils.schemas import SendMessageSchema

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)


# ── Sessions ──────────────────────────────────────────────────────────────────

@chat_bp.route("/sessions", methods=["POST"])
@jwt_required()
def create_session():
    """
    Start a new chat/consultation session.

    Returns:
        201 + session object with initial greeting message
    """
    user_id = get_jwt_identity()
    session_data = ChatService.create_session(user_id)
    return success_response(session_data, "Session created.", 201)


@chat_bp.route("/sessions", methods=["GET"])
@jwt_required()
def list_sessions():
    """
    List all chat sessions for the authenticated user.

    Query params:
        status  — filter by 'active' | 'archived' | 'completed' (optional)
    """
    user_id = get_jwt_identity()
    sessions = ChatService.list_sessions(user_id)

    status_filter = request.args.get("status")
    if status_filter:
        sessions = [s for s in sessions if s["status"] == status_filter]

    return success_response(sessions, f"{len(sessions)} session(s) found.")


@chat_bp.route("/sessions/<string:session_id>", methods=["GET"])
@jwt_required()
def get_session(session_id):
    """
    Retrieve a specific session including all messages.

    Path:
        session_id — UUID of the session
    """
    user_id = get_jwt_identity()
    session_data = ChatService.get_session(session_id, user_id)
    if not session_data:
        return error_response("Session not found.", 404)
    return success_response(session_data, "Session fetched.")


@chat_bp.route("/sessions/<string:session_id>", methods=["DELETE"])
@jwt_required()
def archive_session(session_id):
    """
    Archive (soft-delete) a chat session.

    Path:
        session_id — UUID of the session
    """
    user_id = get_jwt_identity()
    ok = ChatService.archive_session(session_id, user_id)
    if not ok:
        return error_response("Session not found.", 404)
    return success_response(message="Session archived.")


# ── Messaging ─────────────────────────────────────────────────────────────────

@chat_bp.route("/message", methods=["POST"])
@jwt_required()
@validate_json(SendMessageSchema)
def send_message(data):
    """
    Send a user message and receive an AI assistant reply.

    Body:
        session_id  — UUID of the target session
        message     — user's message text

    Returns:
        200 + { message (assistant reply), session (updated), extracted_symptoms }
    """
    user_id = get_jwt_identity()
    result = ChatService.process_message(
        session_id=data["session_id"],
        user_id=user_id,
        user_text=data["message"],
    )

    if isinstance(result, tuple):
        payload, status = result
        return error_response(payload.get("message", "Error"), status)

    return success_response(result, "Message processed.")
