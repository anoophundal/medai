"""
app/utils/helpers.py
---------------------
Reusable helpers:
  - validate_json()   : schema validation decorator
  - success_response()
  - error_response()
  - paginate_query()
"""

import functools
import logging
from flask import request, jsonify
from marshmallow import ValidationError

logger = logging.getLogger(__name__)


def validate_json(schema_class):
    """
    Decorator that validates the incoming JSON body against a Marshmallow schema.
    Injects the validated data as the first argument after `self`/`cls` (or first
    positional arg for plain functions).

    Usage:
        @validate_json(LoginSchema)
        def login(data):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            json_data = request.get_json(silent=True)
            if json_data is None:
                return error_response("Request body must be JSON.", 400)
            schema = schema_class()
            try:
                validated = schema.load(json_data)
            except ValidationError as err:
                # Flatten marshmallow errors into a readable list
                messages = []
                for field, msgs in err.messages.items():
                    for m in msgs:
                        messages.append(f"{field}: {m}")
                return error_response(" | ".join(messages), 422)
            return func(validated, *args, **kwargs)

        return wrapper

    return decorator


def success_response(data: dict | list | None = None, message: str = "Success", status: int = 200):
    """Standard JSON success envelope."""
    payload = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def error_response(message: str, status: int = 400, errors: list | None = None):
    """Standard JSON error envelope."""
    payload = {"success": False, "message": message}
    if errors:
        payload["errors"] = errors
    return jsonify(payload), status


def paginate_query(query, page: int = 1, per_page: int = 20):
    """
    Paginate a SQLAlchemy query and return a pagination envelope.

    Args:
        query: SQLAlchemy Query object.
        page: 1-based page number.
        per_page: Items per page (max 100).

    Returns:
        dict with 'items', 'total', 'page', 'pages', 'per_page'.
    """
    per_page = min(per_page, 100)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return {
        "items": pagination.items,
        "total": pagination.total,
        "page": pagination.page,
        "pages": pagination.pages,
        "per_page": pagination.per_page,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }
