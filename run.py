"""
run.py
------
Application entry point.
  - Development : python run.py
  - Production  : gunicorn "run:app" -w 4 -b 0.0.0.0:5000
"""

import os
import logging
from app import create_app, db
from app.models import User, ChatSession, ChatMessage, DiagnosisResult, SymptomRecord

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = create_app()


@app.cli.command("init-db")
def init_db():
    """Create all database tables."""
    with app.app_context():
        db.create_all()
        print("✅  Database tables created.")


@app.cli.command("seed-db")
def seed_db():
    """Insert demo data for development."""
    import uuid
    from app import bcrypt
    from datetime import date

    with app.app_context():
        db.create_all()

        existing = User.query.filter_by(email="demo@healthcare.ai").first()
        if existing:
            print("ℹ️  Demo user already exists.")
            return

        user = User(
            id=str(uuid.uuid4()),
            email="demo@healthcare.ai",
            password_hash=bcrypt.generate_password_hash("Demo@12345").decode("utf-8"),
            first_name="Alex",
            last_name="Demo",
            date_of_birth=date(1990, 6, 15),
            gender="prefer_not_to_say",
            blood_group="O+",
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()
        print(f"✅  Demo user created: demo@healthcare.ai / Demo@12345")


@app.cli.command("train-models")
def train_models():
    """Pre-train and persist ML models."""
    from app.services.ml_service import MLService
    from pathlib import Path

    with app.app_context():
        model_dir = Path(app.config["MODEL_DIR"])
        print(f"Training ML models → {model_dir}")
        MLService._train_demo_models(model_dir)
        print("✅  Models trained and saved.")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"

    with app.app_context():
        db.create_all()
        print(f"🏥  Healthcare Diagnosis Assistant Backend")
        print(f"🚀  Running on http://localhost:{port}")
        print(f"🔧  Debug mode: {debug}")

    app.run(host="0.0.0.0", port=port, debug=debug)
