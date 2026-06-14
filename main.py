import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router
from admin import router as admin_router
from jobs import router as jobs_router
from secret_client import get_secret

app = FastAPI()

# Session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=get_secret("SESSION_SECRET"),
    session_cookie="session",
    max_age=3600,
    https_only=True,
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
        "dashboard.html", {"request": request, "user": user}
    )
