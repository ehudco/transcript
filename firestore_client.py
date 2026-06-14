from google.cloud import firestore
from datetime import datetime, timezone

db = firestore.Client()

# ── Users ──────────────────────────────────────────

def get_user(email: str):
    doc = db.collection("users").document(email).get()
    return doc.to_dict() if doc.exists else None

def create_pending_user(email: str, sub: str):
    db.collection("users").document(email).set({
        "email": email,
        "sub": sub,
        "status": "pending",
        "role": "user",
        "approved_by": None,
        "approved_at": None,
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
    })

def approve_user(email: str, approved_by: str):
    db.collection("users").document(email).update({
        "status": "active",
        "approved_by": approved_by,
        "approved_at": datetime.now(timezone.utc),
    })

def block_user(email: str):
    db.collection("users").document(email).update({
        "status": "blocked"
    })

def set_user_role(email: str, role: str):
    db.collection("users").document(email).update({"role": role})

def delete_user(email: str):
    db.collection("users").document(email).delete()

def list_users():
    docs = db.collection("users").stream()
    return [doc.to_dict() for doc in docs]

def update_user_last_login(email: str):
    db.collection("users").document(email).update({
        "last_login": datetime.now(timezone.utc)
    })

# ── Jobs ───────────────────────────────────────────

def create_job(job_id: str, user_email: str, file_id: str, file_name: str):
    db.collection("jobs").document(job_id).set({
        "job_id": job_id,
        "user_email": user_email,
        "file_id": file_id,
        "file_name": file_name,
        "status": "queued",
        "srt_content": None,
        "srt_gcs_path": None,
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "completed_at": None,
        "error": None,
    })

def get_job(job_id: str):
    doc = db.collection("jobs").document(job_id).get()
    return doc.to_dict() if doc.exists else None

def list_user_jobs(user_email: str):
    docs = (
        db.collection("jobs")
        .where("user_email", "==", user_email)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .stream()
    )
    return [doc.to_dict() for doc in docs]

def list_all_jobs():
    docs = (
        db.collection("jobs")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .stream()
    )
    return [doc.to_dict() for doc in docs]
