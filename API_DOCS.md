# Healthcare Diagnosis Assistant — Backend API

## Overview

| Property | Value |
|---|---|
| Base URL | `http://localhost:5000/api` |
| Auth | JWT Bearer tokens |
| Content-Type | `application/json` |
| API Version | 1.0 |

All responses follow this envelope:

```json
{
  "success": true,
  "message": "Human-readable status",
  "data": { ... }
}
```

---

## Authentication

### Register
`POST /api/auth/register`

**Body**
```json
{
  "first_name": "Priya",
  "last_name":  "Sharma",
  "email":      "priya@example.com",
  "password":   "Secure@123",
  "gender":     "female",
  "date_of_birth": "1995-03-20"
}
```

**201 Response**
```json
{
  "success": true,
  "message": "Account created successfully.",
  "data": {
    "user": { "id": "...", "email": "...", ... },
    "access_token": "eyJ...",
    "refresh_token": "eyJ..."
  }
}
```

---

### Login
`POST /api/auth/login`

**Body**
```json
{ "email": "priya@example.com", "password": "Secure@123" }
```

**200 Response** — same shape as Register.

Brute-force protection: 5 failures → 15-minute lockout.

---

### Refresh Token
`POST /api/auth/refresh`

**Headers:** `Authorization: Bearer <refresh_token>`

**200 Response**
```json
{ "data": { "access_token": "eyJ..." } }
```

---

### Forgot Password
`POST /api/auth/forgot-password`

**Body** `{ "email": "priya@example.com" }`

Always returns 200 (prevents user enumeration).

---

### Get Current User
`GET /api/auth/me`

**Headers:** `Authorization: Bearer <access_token>`

**200 Response** — user object.

---

## Chat

All endpoints require `Authorization: Bearer <access_token>`.

### Create Session
`POST /api/chat/sessions`

Returns a new session with the opening greeting message.

```json
{
  "data": {
    "id": "uuid",
    "title": "New Consultation",
    "status": "active",
    "messages": [{ "sender": "assistant", "content": "Hello! ..." }],
    "extracted_symptoms": []
  }
}
```

---

### List Sessions
`GET /api/chat/sessions?status=active`

---

### Get Session
`GET /api/chat/sessions/<session_id>`

Returns session + all messages.

---

### Archive Session
`DELETE /api/chat/sessions/<session_id>`

---

### Send Message
`POST /api/chat/message`

**Body**
```json
{
  "session_id": "uuid",
  "message": "I have had a headache and fever for 2 days"
}
```

**200 Response**
```json
{
  "data": {
    "message": { "sender": "assistant", "content": "I've noted: headache, fever..." },
    "session": { "extracted_symptoms": ["headache", "fever"] }
  }
}
```

The assistant will:
1. Extract symptoms from natural language
2. Ask follow-up questions if < 3 symptoms found
3. Prompt for diagnosis when sufficient symptoms collected

---

## Diagnosis

### Run Prediction
`POST /api/diagnosis/predict`

**Body**
```json
{
  "symptoms":    ["fever", "headache", "body_aches", "chills"],
  "session_id":  "uuid",          
  "severity_map": { "fever": 8, "headache": 6 }
}
```

**201 Response**
```json
{
  "data": {
    "id": "uuid",
    "primary_disease": "Influenza (Flu)",
    "primary_confidence": 0.847,
    "risk_level": "medium",
    "severity_score": 62.3,
    "predictions": [
      {
        "disease": "Influenza (Flu)",
        "confidence": 0.847,
        "confidence_pct": 84.7,
        "matched_symptoms": ["fever", "headache", "body_aches", "chills"],
        "description": "A contagious respiratory illness...",
        "risk": "medium"
      },
      { "disease": "Common Cold", "confidence": 0.423, ... }
    ],
    "recommendations": [
      "Rest at home and avoid contact with others",
      "Take antiviral medications if prescribed within 48 hours",
      "..."
    ],
    "disclaimer": "This analysis is for informational purposes only...",
    "processing_time_ms": 42
  }
}
```

---

### Diagnosis History
`GET /api/diagnosis/history?page=1&per_page=10`

---

### Get Single Result
`GET /api/diagnosis/<result_id>`

---

### Symptom Vocabulary
`GET /api/diagnosis/symptoms/list`

Returns 132 supported symptom identifiers with human-readable labels.

---

## Profile

### Get Profile
`GET /api/profile`

### Update Profile
`PUT /api/profile`

**Body** (all optional)
```json
{
  "first_name": "Priya",
  "blood_group": "B+",
  "allergies": "Penicillin",
  "medical_history": "Hypertension diagnosed 2020"
}
```

### Change Password
`POST /api/profile/password`

**Body**
```json
{ "current_password": "Old@123", "new_password": "New@456" }
```

### Symptom History
`GET /api/profile/symptoms?page=1&per_page=20`

### Dashboard Stats
`GET /api/profile/stats`

```json
{
  "data": {
    "total_sessions": 12,
    "total_diagnoses": 8,
    "risk_breakdown": { "low": 4, "medium": 3, "high": 1 },
    "top_symptoms": [
      { "symptom": "Fever", "count": 5 },
      { "symptom": "Headache", "count": 4 }
    ],
    "recent_diagnoses": [ ... ]
  }
}
```

---

## Health Checks

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness probe |
| `GET /api/health/db` | Database connectivity |

---

## Error Codes

| Code | Meaning |
|---|---|
| 400 | Bad request |
| 401 | Unauthorised / expired token |
| 403 | Forbidden / account locked |
| 404 | Resource not found |
| 409 | Conflict (duplicate email) |
| 422 | Validation error |
| 500 | Internal server error |

---

## ML Models

The prediction engine is a **3-model ensemble**:

| Model | Library | Role |
|---|---|---|
| Random Forest | scikit-learn | Robust baseline |
| XGBoost | xgboost | Gradient-boosted trees |
| Logistic Regression | scikit-learn | Calibrated probabilities |

Final score = **35% rule-based Jaccard + 65% average ML probability**.

### Supported Diseases (15)

Common Cold · Influenza · COVID-19 · Pneumonia · Dengue Fever · Malaria ·
Typhoid Fever · Gastroenteritis · Diabetes (Type 2) · Hypertension · Migraine ·
Asthma · Urinary Tract Infection · Anaemia · Anxiety Disorder

### Risk Levels

| Level | Severity Score | Action |
|---|---|---|
| 🟢 Low | < 30 | Monitor, OTC treatment |
| 🟡 Medium | 30–60 | See doctor within 48 h |
| 🔴 High | > 60 | Urgent / emergency care |
