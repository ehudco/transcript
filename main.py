from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router
from admin import router as admin_router
from jobs import router as jobs_router
from secret_client import get_secret

QUEUE_CHECK_INTERVAL = int(os.environ.get("QUEUE_CHECK_INTERVAL", "1800"))  # 30 minutes


async def _queue_watchdog():
    """Periodically check for queued jobs and start the VM if needed."""
    while True:
        await asyncio.sleep(QUEUE_CHECK_INTERVAL)
        try:
            from firestore_client import list_all_jobs
            from compute import get_vm_status, start_vm
            queued = [j for j in list_all_jobs() if j.get("status") == "queued"]
            if queued:
                print(f"[watchdog] {len(queued)} queued job(s) found")
                status = get_vm_status()
                if status in ("TERMINATED", "STOPPED"):
                    print(f"[watchdog] VM is {status} — starting it now")
                    start_vm()
                else:
                    print(f"[watchdog] VM status is {status} — no action needed")
            else:
                print(f"[watchdog] no queued jobs")
        except Exception as e:
            print(f"[watchdog] error: {e}")


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_queue_watchdog())
    yield
    task.cancel()

BUILD_ID = os.environ.get("BUILD_ID", "local")


def _dashboard_context(request):
    """Extra template vars needed by dashboard.html."""
    tokens = request.session.get("oauth_tokens", {})
    picker_api_key = get_secret("PICKER_API_KEY").strip()
    if not picker_api_key:
        raise ValueError("PICKER_API_KEY secret is empty")
    return {
        "google_client_id": get_secret("GOOGLE_CLIENT_ID").strip(),
        "picker_api_key": picker_api_key,
        "oauth_token": tokens.get("token", ""),
    }

app = FastAPI(lifespan=lifespan)

# Trust X-Forwarded-Proto from Cloud Run's proxy so request.url uses https://
if os.environ.get("ENV") != "development":
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.add_middleware(
    SessionMiddleware,
    secret_key=get_secret("SESSION_SECRET"),
    session_cookie="session",
    max_age=3600,
    https_only=os.environ.get("ENV") != "development",
    same_site="lax"
)

templates = Jinja2Templates(directory="templates")
templates.env.globals["build_id"] = BUILD_ID

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(jobs_router)

@app.get("/version")
async def version():
    return {"build_id": os.environ.get("BUILD_ID", "local")}


@app.get("/debug/picker-config")
async def debug_picker_config(request: Request):
    """Temporary debug endpoint — remove after debugging."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    tokens = request.session.get("oauth_tokens", {})
    key = get_secret("PICKER_API_KEY").strip()
    return {
        "key_length": len(key),
        "key_first_8": key[:8],
        "key_last_4": key[-4:],
        "key_has_newline": "\n" in key,
        "key_has_spaces": " " in key,
        "oauth_token_present": bool(tokens.get("token")),
        "oauth_token_first_10": tokens.get("token", "")[:10],
    }


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return RedirectResponse("/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, **_dashboard_context(request)}
    )
