"""
app/services/ml_service.py
---------------------------
Core ML / NLP pipeline:
  1. Symptom extraction from free-text (regex + keyword matching)
  2. Feature vector construction (binary symptom presence)
  3. Disease prediction ensemble (Random Forest + XGBoost + Logistic Regression)
  4. Confidence scoring & risk classification
  5. Explainable AI output (matched symptoms per disease)
  6. Personalised recommendations

The models are trained lazily on first use and cached in memory.
If no persisted model artefact is found, a synthetic dataset is used
to train a demo model in-memory (so the API works out of the box).
"""

import os
import re
import json
import time
import uuid
import logging
import joblib
import numpy as np

from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Symptom vocabulary ────────────────────────────────────────────────────────
# 132 symptoms used as binary feature columns in the ML models
SYMPTOM_VOCABULARY = [
    "fever", "high_fever", "mild_fever", "chills", "sweating", "night_sweats",
    "headache", "severe_headache", "migraine", "dizziness", "vertigo", "fainting",
    "fatigue", "weakness", "body_aches", "muscle_pain", "joint_pain",
    "chest_pain", "chest_tightness", "palpitations", "shortness_of_breath",
    "wheezing", "cough", "dry_cough", "productive_cough", "coughing_blood",
    "sore_throat", "runny_nose", "nasal_congestion", "sneezing", "loss_of_smell",
    "nausea", "vomiting", "diarrhea", "constipation", "abdominal_pain",
    "stomach_cramps", "bloating", "loss_of_appetite", "weight_loss",
    "yellowing_skin", "dark_urine", "pale_stool", "itching",
    "skin_rash", "hives", "redness", "swelling", "bruising",
    "hair_loss", "dry_skin", "excessive_sweating",
    "frequent_urination", "painful_urination", "blood_in_urine",
    "back_pain", "lower_back_pain", "neck_pain", "shoulder_pain",
    "eye_redness", "blurred_vision", "watery_eyes", "eye_pain",
    "ear_pain", "hearing_loss", "ringing_in_ears",
    "confusion", "memory_loss", "difficulty_concentrating",
    "anxiety", "depression", "mood_swings", "irritability",
    "insomnia", "excessive_sleep", "restlessness",
    "numbness", "tingling", "paralysis", "tremors", "seizures",
    "swollen_lymph_nodes", "enlarged_spleen", "enlarged_liver",
    "increased_thirst", "increased_hunger", "slow_healing",
    "cold_hands_feet", "irregular_heartbeat", "high_blood_pressure",
    "pale_skin", "bluish_lips", "rapid_breathing", "shallow_breathing",
    "difficulty_swallowing", "hoarseness", "mouth_sores",
    "tooth_pain", "gum_bleeding",
    "painful_periods", "irregular_periods", "vaginal_discharge",
    "erectile_dysfunction", "testicular_pain",
    "stiff_neck", "stiff_joints", "difficulty_walking",
    "sudden_weight_gain", "puffiness", "swollen_ankles",
    "red_eyes", "sensitivity_to_light", "double_vision",
    "loss_of_taste", "bad_breath", "excessive_thirst",
    "hot_flashes", "vaginal_dryness", "breast_pain",
]

# ── Symptom aliases (natural-language → canonical) ─────────────────────────
SYMPTOM_ALIASES: dict[str, str] = {
    # Fever variants
    "temperature": "fever", "hot": "fever", "high temp": "high_fever",
    "burning": "fever", "pyrexia": "fever",
    # Pain
    "ache": "body_aches", "pain": "body_aches", "hurt": "body_aches",
    "hurting": "body_aches", "painful": "body_aches",
    "head pain": "headache", "head ache": "headache",
    "chest pain": "chest_pain", "heart pain": "chest_pain",
    "back pain": "back_pain", "lower back": "lower_back_pain",
    "stomach pain": "abdominal_pain", "tummy": "abdominal_pain",
    "belly pain": "abdominal_pain", "cramps": "stomach_cramps",
    # Respiratory
    "breathing difficulty": "shortness_of_breath",
    "hard to breathe": "shortness_of_breath",
    "cant breathe": "shortness_of_breath",
    "wheeze": "wheezing", "phlegm": "productive_cough",
    "mucus": "productive_cough", "congestion": "nasal_congestion",
    "blocked nose": "nasal_congestion", "stuffy nose": "nasal_congestion",
    "runny": "runny_nose",
    # GI
    "throw up": "vomiting", "threw up": "vomiting", "puked": "vomiting",
    "sick": "nausea", "queasy": "nausea", "upset stomach": "nausea",
    "loose stools": "diarrhea", "loose motion": "diarrhea",
    "watery stool": "diarrhea",
    # General
    "tired": "fatigue", "exhausted": "fatigue", "lethargic": "fatigue",
    "no energy": "fatigue", "weak": "weakness",
    "dizzy": "dizziness", "lightheaded": "dizziness",
    "spinning": "vertigo", "fainted": "fainting",
    "itchy": "itching", "itch": "itching",
    "rash": "skin_rash", "spots": "skin_rash",
    "swollen": "swelling", "puffy": "puffiness",
    "thirsty": "increased_thirst", "hungry": "increased_hunger",
    "blurry vision": "blurred_vision", "cant see well": "blurred_vision",
    "heart racing": "palpitations", "racing heart": "palpitations",
    "heart pounding": "palpitations",
    "cant sleep": "insomnia", "no sleep": "insomnia",
    "yellow skin": "yellowing_skin", "yellow eyes": "yellowing_skin",
    "jaundice": "yellowing_skin",
    "shaking": "tremors", "shivering": "chills",
    "stiff": "stiff_joints",
    "sore": "body_aches",
}

# ── Disease definitions ────────────────────────────────────────────────────────
DISEASE_PROFILES: dict[str, dict] = {
    "Common Cold": {
        "symptoms": ["runny_nose", "sneezing", "sore_throat", "mild_fever",
                     "cough", "nasal_congestion", "fatigue", "body_aches"],
        "risk": "low",
        "description": "A viral infection of the upper respiratory tract.",
        "recommendations": [
            "Rest and get adequate sleep",
            "Stay hydrated — drink plenty of fluids",
            "Use saline nasal drops to relieve congestion",
            "Consider OTC antihistamines or decongestants",
            "Gargle warm salt water for sore throat",
            "Consult a doctor if symptoms worsen after 10 days",
        ],
    },
    "Influenza (Flu)": {
        "symptoms": ["fever", "high_fever", "headache", "body_aches",
                     "fatigue", "cough", "sore_throat", "chills",
                     "muscle_pain", "weakness"],
        "risk": "medium",
        "description": "A contagious respiratory illness caused by influenza viruses.",
        "recommendations": [
            "Rest at home and avoid contact with others",
            "Take antiviral medications if prescribed within 48 hours",
            "Drink fluids to prevent dehydration",
            "Use OTC fever reducers like paracetamol",
            "Seek emergency care for severe symptoms or difficulty breathing",
            "Get annual flu vaccination to prevent future infections",
        ],
    },
    "COVID-19": {
        "symptoms": ["fever", "dry_cough", "fatigue", "loss_of_smell",
                     "loss_of_taste", "shortness_of_breath", "body_aches",
                     "headache", "sore_throat", "chills"],
        "risk": "high",
        "description": "Coronavirus disease caused by SARS-CoV-2.",
        "recommendations": [
            "Isolate immediately to prevent spread",
            "Get tested for COVID-19",
            "Monitor oxygen levels with a pulse oximeter",
            "Contact your doctor for antiviral treatment options",
            "Seek emergency care if breathing is difficult",
            "Ensure vaccination and booster doses are up to date",
        ],
    },
    "Pneumonia": {
        "symptoms": ["fever", "productive_cough", "chest_pain", "shortness_of_breath",
                     "fatigue", "chills", "wheezing", "rapid_breathing"],
        "risk": "high",
        "description": "Infection causing inflammation in the air sacs of the lungs.",
        "recommendations": [
            "Seek immediate medical attention",
            "Complete the full course of prescribed antibiotics",
            "Rest and avoid physical exertion",
            "Use a humidifier to ease breathing",
            "Take prescribed fever medication",
            "Follow up with your doctor after completing treatment",
        ],
    },
    "Dengue Fever": {
        "symptoms": ["fever", "high_fever", "severe_headache", "body_aches",
                     "joint_pain", "skin_rash", "nausea", "vomiting",
                     "fatigue", "eye_pain"],
        "risk": "high",
        "description": "A mosquito-borne viral disease common in tropical regions.",
        "recommendations": [
            "Seek immediate medical attention",
            "Monitor platelet count regularly",
            "Stay hydrated with ORS or fresh juices",
            "Avoid aspirin and ibuprofen — use paracetamol only",
            "Rest in a mosquito-free environment",
            "Use mosquito nets and repellents to prevent spread",
        ],
    },
    "Malaria": {
        "symptoms": ["fever", "chills", "sweating", "headache", "nausea",
                     "vomiting", "body_aches", "fatigue", "high_fever"],
        "risk": "high",
        "description": "A life-threatening disease caused by Plasmodium parasites.",
        "recommendations": [
            "Seek emergency medical care immediately",
            "Take prescribed anti-malarial medications",
            "Complete the full treatment course",
            "Rest and maintain hydration",
            "Use bed nets and insect repellent",
            "Get a blood smear test for confirmation",
        ],
    },
    "Typhoid Fever": {
        "symptoms": ["fever", "abdominal_pain", "headache", "fatigue",
                     "loss_of_appetite", "nausea", "diarrhea", "constipation",
                     "body_aches", "sweating"],
        "risk": "high",
        "description": "A bacterial infection caused by Salmonella typhi.",
        "recommendations": [
            "See a doctor promptly for antibiotic prescription",
            "Complete the full antibiotic course",
            "Drink only boiled or bottled water",
            "Eat small, easily digestible meals",
            "Practice strict hand hygiene",
            "Consider typhoid vaccination for future prevention",
        ],
    },
    "Gastroenteritis": {
        "symptoms": ["nausea", "vomiting", "diarrhea", "abdominal_pain",
                     "stomach_cramps", "fever", "loss_of_appetite", "fatigue"],
        "risk": "low",
        "description": "Inflammation of the stomach and intestines, usually from infection.",
        "recommendations": [
            "Rehydrate with ORS or clear fluids frequently",
            "Follow the BRAT diet (Banana, Rice, Applesauce, Toast)",
            "Avoid dairy, fatty, and spicy foods temporarily",
            "Rest and avoid solid food until vomiting stops",
            "Seek care if symptoms last more than 3 days",
            "Wash hands thoroughly to prevent spreading",
        ],
    },
    "Diabetes (Type 2)": {
        "symptoms": ["increased_thirst", "frequent_urination", "fatigue",
                     "blurred_vision", "slow_healing", "increased_hunger",
                     "weight_loss", "numbness", "tingling"],
        "risk": "medium",
        "description": "A chronic condition affecting blood sugar regulation.",
        "recommendations": [
            "Consult an endocrinologist for proper diagnosis",
            "Monitor blood sugar levels daily",
            "Follow a low-glycaemic diet",
            "Exercise regularly — at least 30 min/day",
            "Take prescribed medications or insulin as directed",
            "Regular eye, foot, and kidney check-ups are essential",
        ],
    },
    "Hypertension": {
        "symptoms": ["headache", "dizziness", "chest_pain", "palpitations",
                     "shortness_of_breath", "blurred_vision", "nausea",
                     "high_blood_pressure"],
        "risk": "medium",
        "description": "Persistently elevated blood pressure in the arteries.",
        "recommendations": [
            "Monitor blood pressure at home daily",
            "Reduce sodium intake significantly",
            "Exercise regularly and maintain a healthy weight",
            "Avoid alcohol and tobacco",
            "Take prescribed antihypertensives consistently",
            "Manage stress through relaxation techniques",
        ],
    },
    "Migraine": {
        "symptoms": ["severe_headache", "nausea", "vomiting", "sensitivity_to_light",
                     "blurred_vision", "dizziness", "fatigue"],
        "risk": "low",
        "description": "A neurological condition causing severe recurring headaches.",
        "recommendations": [
            "Rest in a quiet, dark room during attacks",
            "Apply a cold or warm compress to the head",
            "Take prescribed triptans or OTC pain relievers",
            "Identify and avoid personal migraine triggers",
            "Maintain a regular sleep schedule",
            "Consult a neurologist for preventive medications",
        ],
    },
    "Asthma": {
        "symptoms": ["wheezing", "shortness_of_breath", "chest_tightness",
                     "cough", "dry_cough", "difficulty_breathing"],
        "risk": "medium",
        "description": "A chronic condition causing airway inflammation and narrowing.",
        "recommendations": [
            "Use prescribed rescue inhaler during attacks",
            "Follow your asthma action plan",
            "Avoid known triggers (dust, smoke, pollen)",
            "Take daily controller medication if prescribed",
            "Monitor peak flow readings regularly",
            "Get annual flu vaccination",
        ],
    },
    "Urinary Tract Infection (UTI)": {
        "symptoms": ["frequent_urination", "painful_urination", "blood_in_urine",
                     "lower_back_pain", "fever", "nausea", "abdominal_pain"],
        "risk": "medium",
        "description": "A bacterial infection of the urinary system.",
        "recommendations": [
            "See a doctor for antibiotic prescription",
            "Drink plenty of water to flush bacteria",
            "Complete the full antibiotic course",
            "Avoid holding urine for long periods",
            "Wipe front-to-back after using the toilet",
            "Avoid irritants like caffeine and alcohol during infection",
        ],
    },
    "Anaemia": {
        "symptoms": ["fatigue", "weakness", "pale_skin", "shortness_of_breath",
                     "dizziness", "cold_hands_feet", "headache", "palpitations"],
        "risk": "medium",
        "description": "A condition where there aren't enough healthy red blood cells.",
        "recommendations": [
            "Get blood tests (CBC) to confirm and identify type",
            "Increase iron-rich foods (spinach, lentils, red meat)",
            "Take prescribed iron or B12 supplements",
            "Consume vitamin C to enhance iron absorption",
            "Treat the underlying cause if identified",
            "Follow up with a haematologist if severe",
        ],
    },
    "Anxiety Disorder": {
        "symptoms": ["anxiety", "palpitations", "shortness_of_breath", "sweating",
                     "dizziness", "insomnia", "restlessness", "headache",
                     "fatigue", "muscle_pain"],
        "risk": "low",
        "description": "A mental health disorder characterised by excessive worry and fear.",
        "recommendations": [
            "Speak with a licensed mental health professional",
            "Practice mindfulness and deep breathing exercises",
            "Maintain a regular sleep schedule",
            "Reduce caffeine and alcohol consumption",
            "Exercise regularly to manage stress hormones",
            "Consider Cognitive Behavioural Therapy (CBT)",
        ],
    },
}


class MLService:
    """
    Singleton-like ML service.  Models are loaded/trained once and
    cached as class attributes.
    """

    _symptom_extractor = None     # NLP/regex extractor (stateless)
    _random_forest = None
    _xgboost = None
    _logistic = None
    _feature_columns: list[str] = SYMPTOM_VOCABULARY
    _models_loaded: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def extract_symptoms(cls, text: str) -> list[str]:
        """
        Extract canonical symptom names from free-form user text.
        Uses alias matching + direct vocabulary search.
        """
        text = text.lower()
        # Remove punctuation
        text = re.sub(r"[^\w\s]", " ", text)
        found: set[str] = set()

        # 1. Alias pass
        for alias, canonical in SYMPTOM_ALIASES.items():
            if alias in text:
                found.add(canonical)

        # 2. Direct vocabulary pass
        for symptom in SYMPTOM_VOCABULARY:
            readable = symptom.replace("_", " ")
            if readable in text or symptom in text:
                found.add(symptom)

        return list(found)

    @classmethod
    def predict(cls, symptoms: list[str], user_age: int = 30, user_gender: str = "unknown") -> dict:
        """
        Run the full prediction pipeline.

        Args:
            symptoms: List of canonical symptom strings.
            user_age: Patient age (used for risk adjustment).
            user_gender: 'male' | 'female' | 'other' | 'unknown'

        Returns:
            Full prediction result dict.
        """
        start = time.time()

        if not symptoms:
            return cls._empty_result()

        cls._ensure_models_loaded()

        # Build feature vector
        feature_vector = cls._build_feature_vector(symptoms)

        # Run ensemble
        predictions = cls._run_ensemble(feature_vector, symptoms)

        # Risk classification
        severity_score = cls._compute_severity_score(symptoms, predictions, user_age)
        risk_level = cls._classify_risk(severity_score, predictions)

        # Recommendations for top disease
        top_disease = predictions[0]["disease"] if predictions else "Unknown"
        recommendations = cls._get_recommendations(top_disease, risk_level)

        elapsed_ms = int((time.time() - start) * 1000)

        return {
            "id": str(uuid.uuid4()),
            "predictions": predictions,
            "primary_disease": top_disease,
            "primary_confidence": predictions[0]["confidence"] if predictions else 0.0,
            "risk_level": risk_level,
            "severity_score": round(severity_score, 1),
            "recommendations": recommendations,
            "disclaimer": (
                "This analysis is generated by an AI model for informational purposes only. "
                "It is NOT a medical diagnosis. Please consult a licensed healthcare professional "
                "for proper evaluation and treatment."
            ),
            "model_version": "v1.0-ensemble",
            "processing_time_ms": elapsed_ms,
        }

    # ── Private: feature engineering ──────────────────────────────────────────

    @classmethod
    def _build_feature_vector(cls, symptoms: list[str]) -> np.ndarray:
        """Create a binary feature vector from symptom list."""
        vector = np.zeros(len(cls._feature_columns), dtype=np.float32)
        for i, col in enumerate(cls._feature_columns):
            if col in symptoms:
                vector[i] = 1.0
        return vector.reshape(1, -1)

    # ── Private: ensemble prediction ──────────────────────────────────────────

    @classmethod
    def _run_ensemble(cls, feature_vector: np.ndarray, symptoms: list[str]) -> list[dict]:
        """
        Combine rule-based scoring with ML models.
        Falls back to pure rule-based if models aren't available.
        """
        # Rule-based scoring (always available)
        rule_scores = cls._rule_based_scores(symptoms)

        # Merge with ML scores if available
        if cls._models_loaded and cls._random_forest is not None:
            try:
                rf_proba = cls._random_forest.predict_proba(feature_vector)[0]
                xgb_proba = cls._xgboost.predict_proba(feature_vector)[0]
                lr_proba = cls._logistic.predict_proba(feature_vector)[0]
                ml_scores = cls._merge_ml_scores(rf_proba, xgb_proba, lr_proba)
                final_scores = cls._blend_scores(rule_scores, ml_scores)
            except Exception as e:
                logger.warning("ML model inference failed, using rule-based: %s", e)
                final_scores = rule_scores
        else:
            final_scores = rule_scores

        # Build output list
        results = []
        for disease, score in sorted(final_scores.items(), key=lambda x: -x[1]):
            if score < 0.05:
                continue
            profile = DISEASE_PROFILES.get(disease, {})
            matched = [s for s in symptoms if s in profile.get("symptoms", [])]
            results.append({
                "disease": disease,
                "confidence": round(min(score, 0.97), 4),
                "confidence_pct": round(min(score * 100, 97), 1),
                "matched_symptoms": matched,
                "total_disease_symptoms": len(profile.get("symptoms", [])),
                "description": profile.get("description", ""),
                "risk": profile.get("risk", "unknown"),
            })

        return results[:5]  # top 5 only

    @classmethod
    def _rule_based_scores(cls, symptoms: list[str]) -> dict[str, float]:
        """Jaccard-like overlap score for each disease profile."""
        scores: dict[str, float] = {}
        symptom_set = set(symptoms)
        for disease, profile in DISEASE_PROFILES.items():
            disease_symptoms = set(profile["symptoms"])
            if not disease_symptoms:
                continue
            intersection = symptom_set & disease_symptoms
            union = symptom_set | disease_symptoms
            jaccard = len(intersection) / len(union) if union else 0.0
            # Weight by proportion of disease symptoms matched
            coverage = len(intersection) / len(disease_symptoms)
            scores[disease] = (jaccard * 0.4 + coverage * 0.6)
        return scores

    @classmethod
    def _merge_ml_scores(cls, rf, xgb, lr) -> dict[str, float]:
        """Average the three model probability arrays into a disease→score dict."""
        diseases = list(DISEASE_PROFILES.keys())
        avg = (np.array(rf) + np.array(xgb) + np.array(lr)) / 3.0
        return {d: float(avg[i]) for i, d in enumerate(diseases) if i < len(avg)}

    @classmethod
    def _blend_scores(cls, rule: dict, ml: dict, rule_weight=0.35, ml_weight=0.65) -> dict:
        all_keys = set(rule) | set(ml)
        return {
            k: rule.get(k, 0) * rule_weight + ml.get(k, 0) * ml_weight
            for k in all_keys
        }

    # ── Private: risk & recommendations ──────────────────────────────────────

    @classmethod
    def _compute_severity_score(
        cls, symptoms: list[str], predictions: list[dict], age: int
    ) -> float:
        base = len(symptoms) * 5  # 5 pts per symptom

        # High-severity symptom bonus
        high_severity = {
            "coughing_blood", "chest_pain", "shortness_of_breath",
            "seizures", "paralysis", "confusion", "high_fever",
            "blood_in_urine", "severe_headache",
        }
        base += sum(10 for s in symptoms if s in high_severity)

        # Confidence bonus
        if predictions:
            base += predictions[0]["confidence"] * 20

        # Age adjustment
        if age > 60:
            base *= 1.15
        elif age < 12:
            base *= 1.1

        return min(base, 100.0)

    @classmethod
    def _classify_risk(cls, score: float, predictions: list[dict]) -> str:
        # Disease-level risk override
        if predictions:
            top_disease_risk = predictions[0].get("risk", "low")
            if top_disease_risk == "high":
                return "high"

        if score >= 60:
            return "high"
        elif score >= 30:
            return "medium"
        return "low"

    @classmethod
    def _get_recommendations(cls, disease: str, risk_level: str) -> list[str]:
        profile = DISEASE_PROFILES.get(disease, {})
        recs = list(profile.get("recommendations", []))

        # Append universal risk-level advice
        if risk_level == "high":
            recs.append("⚠️ Seek emergency or urgent medical care as soon as possible.")
        elif risk_level == "medium":
            recs.append("Schedule an appointment with your doctor within 24–48 hours.")
        else:
            recs.append("Monitor your symptoms; consult a doctor if they worsen.")

        return recs

    # ── Private: model loading / training ────────────────────────────────────

    @classmethod
    def _ensure_models_loaded(cls) -> None:
        if cls._models_loaded:
            return

        try:
            from flask import current_app
            model_dir = Path(current_app.config.get("MODEL_DIR", "app/ml/models"))
        except RuntimeError:
            model_dir = Path("app/ml/models")

        rf_path = model_dir / "random_forest.pkl"
        xgb_path = model_dir / "xgboost.pkl"
        lr_path = model_dir / "logistic.pkl"

        if rf_path.exists() and xgb_path.exists() and lr_path.exists():
            logger.info("Loading persisted ML models from %s", model_dir)
            cls._random_forest = joblib.load(rf_path)
            cls._xgboost = joblib.load(xgb_path)
            cls._logistic = joblib.load(lr_path)
            cls._models_loaded = True
            logger.info("Models loaded successfully.")
        else:
            logger.info("No persisted models found — training in-memory demo models.")
            cls._train_demo_models(model_dir)

    @classmethod
    def _train_demo_models(cls, model_dir: Path) -> None:
        """
        Train lightweight demo models on a synthetic dataset derived
        from the disease profiles.  Saves artefacts to disk.
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from xgboost import XGBClassifier

        diseases = list(DISEASE_PROFILES.keys())
        n_diseases = len(diseases)
        n_features = len(SYMPTOM_VOCABULARY)

        # Build synthetic training set:
        # For each disease, generate 40 positive samples (with noise)
        # and 10 negative samples.
        X_rows, y_rows = [], []
        rng = np.random.default_rng(42)

        for idx, (disease, profile) in enumerate(DISEASE_PROFILES.items()):
            sym_indices = [
                SYMPTOM_VOCABULARY.index(s)
                for s in profile["symptoms"]
                if s in SYMPTOM_VOCABULARY
            ]
            # Positive samples
            for _ in range(40):
                row = np.zeros(n_features, dtype=np.float32)
                # Always set primary symptoms
                for si in sym_indices:
                    row[si] = 1.0 if rng.random() > 0.15 else 0.0
                # Add random noise symptoms
                noise = rng.integers(0, n_features, size=rng.integers(0, 3))
                row[noise] = 1.0
                X_rows.append(row)
                y_rows.append(idx)
            # Negative samples (random)
            for _ in range(10):
                row = np.zeros(n_features, dtype=np.float32)
                noise = rng.integers(0, n_features, size=rng.integers(2, 6))
                row[noise] = 1.0
                X_rows.append(row)
                y_rows.append(rng.integers(0, n_diseases))

        X = np.array(X_rows)
        y = np.array(y_rows)

        logger.info("Training demo models on %d synthetic samples…", len(X))

        rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        rf.fit(X, y)

        xgb = XGBClassifier(
            n_estimators=100, random_state=42,
            use_label_encoder=False, eval_metric="mlogloss",
            verbosity=0,
        )
        xgb.fit(X, y)

        lr = LogisticRegression(max_iter=500, random_state=42)
        lr.fit(X, y)

        cls._random_forest = rf
        cls._xgboost = xgb
        cls._logistic = lr
        cls._models_loaded = True

        # Persist to disk
        model_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(rf, model_dir / "random_forest.pkl")
        joblib.dump(xgb, model_dir / "xgboost.pkl")
        joblib.dump(lr, model_dir / "logistic.pkl")

        # Save disease label map
        with open(model_dir / "label_map.json", "w") as f:
            json.dump({str(i): d for i, d in enumerate(diseases)}, f, indent=2)

        logger.info("Demo models trained and saved to %s", model_dir)

    @classmethod
    def _empty_result(cls) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "predictions": [],
            "primary_disease": None,
            "primary_confidence": 0.0,
            "risk_level": "low",
            "severity_score": 0.0,
            "recommendations": [
                "Please describe your symptoms in more detail.",
                "Consult a healthcare professional for any health concerns.",
            ],
            "disclaimer": (
                "This analysis is generated by an AI model for informational purposes only. "
                "It is NOT a medical diagnosis."
            ),
            "model_version": "v1.0-ensemble",
            "processing_time_ms": 0,
        }
