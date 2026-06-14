import uuid
import json
import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from firestore_client import create_job, get_job, list_user_jobs
import re

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "whisper-project-462317")
TOPIC_ID = "transcription-jobs"
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

def parse_drive_file_id(url: str) -> str | None:
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def require_login(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return None

@router.post("/submit")
async def submit_job(request: Request, drive_url: str = Form(...)):
    guard = require_login(request)
    if guard:
        return guard

    user = request.session["user"]
    file_id = parse_drive_file_id(drive_url)

    if not file_id:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user,
                "error": "Could not parse Drive file ID from URL."
            }
        )

    job_id = str(uuid.uuid4())
    create_job(
        job_id=job_id,
        user_email=user["email"],
        file_id=file_id,
        file_name=drive_url
    )

    if TEST_MODE:
        print(f"[TEST MODE] Skipping VM start and Pub/Sub publish for job {job_id}")
    else:
        # Start VM if not running
        from compute import get_vm_status, start_vm
        status = get_vm_status()
        if status in ("TERMINATED", "STOPPED"):
            start_vm()

        # Publish job to Pub/Sub
        from google.cloud import pubsub_v1
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
        message = {
            "job_id": job_id,
            "file_id": file_id,
            "user_email": user["email"],
            "oauth_tokens": request.session.get("oauth_tokens"),
        }
        publisher.publish(
            topic_path,
            json.dumps(message).encode("utf-8")
        )

    return RedirectResponse(f"/job/{job_id}", status_code=303)

@router.get("/job/{job_id}", response_class=HTMLResponse)
async def job_status(request: Request, job_id: str):
    guard = require_login(request)
    if guard:
        return guard

    user = request.session["user"]
    job = get_job(job_id)

    if not job:
        return HTMLResponse("Job not found", status_code=404)

    if job["user_email"] != user["email"] and user["role"] != "admin":
        return HTMLResponse("Forbidden", status_code=403)

    return templates.TemplateResponse(
        "job_status.html",
        {"request": request, "user": user, "job": job}
    )

@router.get("/my-jobs", response_class=HTMLResponse)
async def my_jobs(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    user = request.session["user"]
    jobs = list_user_jobs(user["email"])
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "jobs": jobs}
    )
