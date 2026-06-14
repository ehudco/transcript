from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from firestore_client import (
    list_users, approve_user, block_user,
    delete_user, set_user_role, list_all_jobs
)

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

def require_admin(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    if user.get("role") != "admin":
        return HTMLResponse("Forbidden", status_code=403)
    return None

@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request):
    guard = require_admin(request)
    if guard:
        return guard
    users = list_users()
    jobs = list_all_jobs()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": request.session["user"],
            "users": users,
            "jobs": jobs,
        }
    )

@router.post("/approve")
async def approve(request: Request, email: str = Form(...)):
    guard = require_admin(request)
    if guard:
        return guard
    approve_user(email, approved_by=request.session["user"]["email"])
    return RedirectResponse("/admin/", status_code=303)

@router.post("/block")
async def block(request: Request, email: str = Form(...)):
    guard = require_admin(request)
    if guard:
        return guard
    block_user(email)
    return RedirectResponse("/admin/", status_code=303)

@router.post("/delete")
async def delete(request: Request, email: str = Form(...)):
    guard = require_admin(request)
    if guard:
        return guard
    delete_user(email)
    return RedirectResponse("/admin/", status_code=303)

@router.post("/set-role")
async def set_role(
    request: Request,
    email: str = Form(...),
    role: str = Form(...)
):
    guard = require_admin(request)
    if guard:
        return guard
    if role not in ("admin", "user"):
        return HTMLResponse("Invalid role", status_code=400)
    set_user_role(email, role)
    return RedirectResponse("/admin/", status_code=303)
