from .auth import auth_bp
from .chat import chat_bp
from .diagnosis import diagnosis_bp
from .profile import profile_bp
from .health import health_bp

__all__ = ["auth_bp", "chat_bp", "diagnosis_bp", "profile_bp", "health_bp"]
