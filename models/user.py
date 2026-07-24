"""
app/models/user.py
------------------
User model — stores credentials, profile, and security fields.
"""

from datetime import datetime, timezone
from app import db


class User(db.Model):
    """
    Core user record.

    Columns
    -------
    id              Primary key (UUID string)
    email           Unique login identifier
    password_hash   bcrypt digest — never store plaintext
    first_name      Given name
    last_name       Family name
    date_of_birth   Used to derive age at diagnosis time
    gender          'male' | 'female' | 'other' | 'prefer_not_to_say'
    blood_group     e.g. "A+" — optional
    allergies       Free-text; comma-separated
    medical_history Free-text; existing conditions
    is_verified     Email-verified flag (future: email confirmation flow)
    is_active       Soft-delete / account suspension
    login_attempts  Counter for brute-force protection
    locked_until    Datetime after which login is re-allowed
    last_login      Audit field
    created_at      Record creation timestamp
    updated_at      Last modification timestamp
    """

    __tablename__ = "users"

    # ── Identity ─────────────────────────────────────────────────────────────
    id = db.Column(db.String(36), primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)

    # ── Profile ───────────────────────────────────────────────────────────────
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    blood_group = db.Column(db.String(5), nullable=True)
    allergies = db.Column(db.Text, nullable=True)
    medical_history = db.Column(db.Text, nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # ── Security ─────────────────────────────────────────────────────────────
    login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    chat_sessions = db.relationship(
        "ChatSession", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    diagnosis_results = db.relationship(
        "DiagnosisResult", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    symptom_records = db.relationship(
        "SymptomRecord", backref="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = datetime.now(timezone.utc).date()
        dob = self.date_of_birth
        return (
            today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        )

    @property
    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return datetime.now(timezone.utc) < self.locked_until.replace(tzinfo=timezone.utc)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Return a JSON-serialisable dict."""
        data = {
            "id": self.id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "age": self.age,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "gender": self.gender,
            "blood_group": self.blood_group,
            "allergies": self.allergies,
            "medical_history": self.medical_history,
            "phone_number": self.phone_number,
            "is_verified": self.is_verified,
            "is_active": self.is_active,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_sensitive:
            data["login_attempts"] = self.login_attempts
            data["locked_until"] = self.locked_until.isoformat() if self.locked_until else None
        return data

    def __repr__(self) -> str:
        return f"<User {self.email}>"
