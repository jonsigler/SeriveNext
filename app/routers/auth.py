from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import (
    hash_password,
    login_user,
    logout_user,
    verify_password,
)
from app.templating import ctx, templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", ctx(request, error=None))


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            ctx(request, error="Invalid email or password."),
            status_code=400,
        )
    login_user(request, user)
    # Agents and admins land in the console; end users in the portal.
    target = "/agent" if user.is_agent else "/portal"
    return RedirectResponse(target, status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", ctx(request, error=None))


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    department: str = Form(""),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    if len(password) < 6:
        return templates.TemplateResponse(
            "register.html",
            ctx(request, error="Password must be at least 6 characters."),
            status_code=400,
        )
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        return templates.TemplateResponse(
            "register.html",
            ctx(request, error="An account with that email already exists."),
            status_code=400,
        )
    user = User(
        email=email,
        full_name=full_name.strip(),
        department=department.strip() or None,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    login_user(request, user)
    return RedirectResponse("/portal", status_code=303)
