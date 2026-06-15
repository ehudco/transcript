import os
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from firestore_client import get_user, update_user_last_login, create_pending_user
from secret_client import get_secret
import json

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file",
]

def get_flow(request: Request) -> Flow:
    if os.environ.get("ENV") == "development":
        base_url = str(request.base_url)
    else:
        base_url = str(request.base_url).replace("http://", "https://")
    redirect_uri = base_url + "auth/callback"

    client_config = {
        "web": {
            "client_id": get_secret("GOOGLE_CLIENT_ID"),
            "client_secret": get_secret("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    return flow


@router.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    user = request.session.get("user")
    if user:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/auth/google")
async def auth_google(request: Request):
    flow = get_flow(request)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )
    request.session["oauth_state"] = state
    return RedirectResponse(auth_url)

@router.get("/auth/callback")
async def auth_callback(request: Request):
    state = request.session.get("oauth_state")
    flow = get_flow(request)
    try:
        flow.fetch_token(
            authorization_response=str(request.url),
            state=state
        )
    except Exception as exc:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"Authentication failed: {exc}"}
        )

    credentials = flow.credentials
    try:
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            google_requests.Request(),
            get_secret("GOOGLE_CLIENT_ID")
        )
    except Exception as exc:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": f"Token verification failed: {exc}"}
        )

    email = id_info.get("email")
    sub = id_info.get("sub")
    email_verified = id_info.get("email_verified", False)

    # Reject unverified emails
    if not email_verified:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Email not verified."}
        )

    # Check allowlist
    user_doc = get_user(email)

    if not user_doc:
        # Create pending user
        create_pending_user(email, sub)
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Your account is pending approval. "
                         "Please contact an administrator."
            }
        )

    if user_doc.get("status") != "active":
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": f"Your account status is: "
                         f"{user_doc.get('status')}. "
                         f"Contact an administrator."
            }
        )

    # Store session
    request.session["user"] = {
        "email": email,
        "sub": sub,
        "role": user_doc.get("role", "user"),
        "name": id_info.get("name", email),
    }

    # Store OAuth tokens for Drive access
    request.session["oauth_tokens"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or []),
    }

    update_user_last_login(email)

    return RedirectResponse("/dashboard")

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
