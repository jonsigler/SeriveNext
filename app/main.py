from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import agent, api, auth, cmdb, kb, portal
from app.templating import TEMPLATE_DIR

settings = get_settings()

app = FastAPI(title="SeriveNext", version="0.1.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 24 * 7,
)

app.mount(
    "/static",
    StaticFiles(directory=str(TEMPLATE_DIR.parent / "static")),
    name="static",
)

app.include_router(auth.router, tags=["auth"])
app.include_router(portal.router, tags=["portal"])
app.include_router(agent.router, tags=["agent"])
app.include_router(cmdb.router, tags=["cmdb"])
app.include_router(kb.router, tags=["kb"])
app.include_router(api.router, tags=["api"])


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/")
def root(request: Request):
    uid = request.session.get("user_id")
    if not uid:
        return RedirectResponse("/login", status_code=303)
    # Route based on role - agents to console, everyone else to portal.
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        user = db.get(User, uid)
    if user and user.is_agent:
        return RedirectResponse("/agent", status_code=303)
    return RedirectResponse("/portal", status_code=303)


@app.get("/healthz")
def health():
    return {"ok": True, "version": "0.1.0", "ai_provider": settings.ai_provider}
