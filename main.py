from dotenv import load_dotenv
load_dotenv()

import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router
from admin import router as admin_router
from jobs import router as jobs_router
from secret_client import get_secret

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

app = FastAPI()

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

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(jobs_router)

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
