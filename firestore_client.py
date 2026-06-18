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

def save_user_refresh_token(email: str, refresh_token: str):
    db.collection("users").document(email).update({
        "refresh_token": refresh_token,
    })

def get_user_refresh_token(email: str) -> str | None:
    doc = db.collection("users").document(email).get()
    return doc.to_dict().get("refresh_token") if doc.exists else None

# ── Jobs ───────────────────────────────────────────

def create_job(job_id: str, user_email: str, file_id: str, file_name: str, oauth_tokens: dict = None):
    db.collection("jobs").document(job_id).set({
        "job_id": job_id,
        "user_email": user_email,
        "file_id": file_id,
        "file_name": file_name,
        "status": "queued",
        "oauth_tokens": oauth_tokens,
        "srt_content": None,
        "srt_translated": None,
        "translation_status": None,
        "srt_gcs_path": None,
        "created_at": datetime.now(timezone.utc),
        "started_at": None,
        "completed_at": None,
        "error": None,
    })


def list_completed_untranslated_jobs():
    docs = (
        db.collection("jobs")
        .where("status", "==", "completed")
        .stream()
    )
    return [
        d.to_dict() for d in docs
        if d.to_dict().get("translation_status") is None
    ]


def set_translation_status(job_id: str, status: str):
    db.collection("jobs").document(job_id).update({"translation_status": status})


def complete_translation(job_id: str, srt_translated: str, csv_content: str):
    db.collection("jobs").document(job_id).update({
        "srt_translated": srt_translated,
        "csv_content": csv_content,
        "translation_status": "completed",
    })

def get_job(job_id: str):
    doc = db.collection("jobs").document(job_id).get()
    return doc.to_dict() if doc.exists else None

def list_user_jobs(user_email: str):
    docs = (
        db.collection("jobs")
        .where("user_email", "==", user_email)
        .stream()
    )
    results = [doc.to_dict() for doc in docs]
    results.sort(key=lambda j: j.get("created_at") or datetime.min, reverse=True)
    return results

def list_all_jobs():
    docs = db.collection("jobs").stream()
    results = [doc.to_dict() for doc in docs]
    results.sort(key=lambda j: j.get("created_at") or datetime.min, reverse=True)
    return results

def claim_queued_job() -> dict | None:
    """Atomically claim one queued job, returning it or None if none available."""
    docs = list(
        db.collection("jobs").where("status", "==", "queued").limit(1).stream()
    )
    if not docs:
        return None
    ref = docs[0].reference
    job = docs[0].to_dict()
    ref.update({
        "status": "processing",
        "started_at": datetime.now(timezone.utc),
    })
    job["status"] = "processing"
    return job

def complete_job(job_id: str, srt_content: str):
    db.collection("jobs").document(job_id).update({
        "status": "completed",
        "srt_content": srt_content,
        "oauth_tokens": None,
        "completed_at": datetime.now(timezone.utc),
    })

def fail_job(job_id: str, error: str):
    db.collection("jobs").document(job_id).update({
        "status": "error",
        "error": error,
        "oauth_tokens": None,
        "completed_at": datetime.now(timezone.utc),
    })
