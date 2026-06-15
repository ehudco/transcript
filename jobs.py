import asyncio
import uuid
import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from firestore_client import create_job, get_job, list_user_jobs
from secret_client import get_secret
import re

router = APIRouter()
templates = Jinja2Templates(directory="templates")

TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"
VM_START_DELAY = int(os.environ.get("VM_START_DELAY", "300"))  # 5 minutes

_vm_start_task: asyncio.Task | None = None


async def _delayed_vm_start():
    await asyncio.sleep(VM_START_DELAY)
    from compute import get_vm_status, start_vm
    status = get_vm_status()
    if status in ("TERMINATED", "STOPPED"):
        print(f"[jobs] starting VM after {VM_START_DELAY}s delay")
        start_vm()
    global _vm_start_task
    _vm_start_task = None

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
async def submit_job(request: Request, file_id: str = Form(...), file_name: str = Form(...)):
    guard = require_login(request)
    if guard:
        return guard

    user = request.session["user"]

    if not file_id:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user,
                "error": "No file selected."
            }
        )

    job_id = str(uuid.uuid4())
    create_job(
        job_id=job_id,
        user_email=user["email"],
        file_id=file_id,
        file_name=file_name,
        oauth_tokens=request.session.get("oauth_tokens"),
    )

    if TEST_MODE:
        print(f"[TEST MODE] Skipping VM start for job {job_id}")
    else:
        global _vm_start_task
        from compute import get_vm_status
        status = get_vm_status()
        if status in ("TERMINATED", "STOPPED"):
            if _vm_start_task is None or _vm_start_task.done():
                print(f"[jobs] VM is {status}, scheduling start in {VM_START_DELAY}s")
                _vm_start_task = asyncio.create_task(_delayed_vm_start())

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

@router.get("/job/{job_id}/download")
async def download_srt(request: Request, job_id: str):
    guard = require_login(request)
    if guard:
        return guard

    user = request.session["user"]
    job = get_job(job_id)

    if not job:
        return HTMLResponse("Job not found", status_code=404)

    if job["user_email"] != user["email"] and user["role"] != "admin":
        return HTMLResponse("Forbidden", status_code=403)

    if job.get("status") != "completed" or not job.get("srt_content"):
        return HTMLResponse("SRT not available", status_code=404)

    filename = job.get("file_name", job_id)
    # Use the original file name stem with .srt extension
    stem = os.path.splitext(os.path.basename(filename))[0] or job_id
    return Response(
        content=job["srt_content"],
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{stem}.srt"'},
    )


@router.get("/my-jobs", response_class=HTMLResponse)
async def my_jobs(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    user = request.session["user"]
    jobs = list_user_jobs(user["email"])
    tokens = request.session.get("oauth_tokens", {})
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "jobs": jobs,
            "google_client_id": get_secret("GOOGLE_CLIENT_ID"),
            "picker_api_key": get_secret("PICKER_API_KEY"),
            "oauth_token": tokens.get("token", ""),
        }
    )
