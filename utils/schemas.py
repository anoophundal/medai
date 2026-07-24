"""
app/utils/schemas.py
---------------------
Marshmallow schemas for input validation and serialisation.
All route handlers deserialise + validate using these schemas
before passing data to service layers.
"""

from datetime import date
from marshmallow import Schema, fields, validate, validates, ValidationError, pre_load


# ── Auth schemas ──────────────────────────────────────────────────────────────

class RegisterSchema(Schema):
    first_name = fields.Str(required=True, validate=validate.Length(min=2, max=80))
    last_name  = fields.Str(required=True, validate=validate.Length(min=2, max=80))
    email      = fields.Email(required=True)
    password   = fields.Str(required=True, validate=validate.Length(min=8, max=128), load_only=True)
    gender     = fields.Str(
        load_default=None,
        validate=validate.OneOf(["male", "female", "other", "prefer_not_to_say"]),
    )
    date_of_birth = fields.Date(load_default=None)
    phone_number  = fields.Str(load_default=None, validate=validate.Length(max=20))

    @validates("password")
    def validate_password_strength(self, value):
        if not any(c.isupper() for c in value):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in value):
            raise ValidationError("Password must contain at least one digit.")

    @pre_load
    def strip_strings(self, data, **kwargs):
        return {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}


class LoginSchema(Schema):
    email    = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True)

    @pre_load
    def strip_strings(self, data, **kwargs):
        return {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}


class ForgotPasswordSchema(Schema):
    email = fields.Email(required=True)


class ResetPasswordSchema(Schema):
    token        = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=8, max=128))


# ── Profile schemas ───────────────────────────────────────────────────────────

class UpdateProfileSchema(Schema):
    first_name    = fields.Str(validate=validate.Length(min=2, max=80))
    last_name     = fields.Str(validate=validate.Length(min=2, max=80))
    date_of_birth = fields.Date()
    gender        = fields.Str(
        validate=validate.OneOf(["male", "female", "other", "prefer_not_to_say"])
    )
    blood_group   = fields.Str(validate=validate.Length(max=5))
    allergies     = fields.Str(validate=validate.Length(max=1000))
    medical_history = fields.Str(validate=validate.Length(max=5000))
    phone_number  = fields.Str(validate=validate.Length(max=20))

    @pre_load
    def strip_strings(self, data, **kwargs):
        return {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}


class ChangePasswordSchema(Schema):
    current_password = fields.Str(required=True, load_only=True)
    new_password     = fields.Str(
        required=True, load_only=True, validate=validate.Length(min=8, max=128)
    )

    @validates("new_password")
    def validate_strength(self, value):
        if not any(c.isupper() for c in value):
            raise ValidationError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in value):
            raise ValidationError("Password must contain at least one digit.")


# ── Chat schemas ──────────────────────────────────────────────────────────────

class SendMessageSchema(Schema):
    message    = fields.Str(required=True, validate=validate.Length(min=1, max=5000))
    session_id = fields.Str(required=True)

    @pre_load
    def strip_message(self, data, **kwargs):
        if "message" in data and isinstance(data["message"], str):
            data["message"] = data["message"].strip()
        return data


# ── Diagnosis schemas ─────────────────────────────────────────────────────────

class DiagnoseSchema(Schema):
    symptoms   = fields.List(
        fields.Str(validate=validate.Length(min=1, max=200)),
        required=True,
        validate=validate.Length(min=1, max=50),
    )
    session_id = fields.Str(load_default=None)
    severity_map = fields.Dict(
        keys=fields.Str(),
        values=fields.Int(validate=validate.Range(min=1, max=10)),
        load_default={},
    )
