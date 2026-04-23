from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KBArticle, User
from app.security import require_agent
from app.templating import ctx, templates

router = APIRouter(prefix="/agent/kb")


@router.get("")
def kb_list(request: Request, user: User = Depends(require_agent), db: Session = Depends(get_db)):
    articles = db.scalars(select(KBArticle).order_by(KBArticle.updated_at.desc())).all()
    return templates.TemplateResponse("agent/kb_list.html", ctx(request, articles=articles))


@router.get("/new")
def kb_new(request: Request, user: User = Depends(require_agent)):
    return templates.TemplateResponse("agent/kb_form.html", ctx(request, article=None))


@router.post("/new")
def kb_create(
    request: Request,
    title: str = Form(...),
    category: str = Form("general"),
    summary: str = Form(...),
    body: str = Form(...),
    keywords: str = Form(""),
    published: str = Form(""),
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    article = KBArticle(
        title=title.strip(),
        category=category.strip() or "general",
        summary=summary.strip(),
        body=body.strip(),
        keywords=keywords.strip(),
        published=bool(published),
        author_id=user.id,
    )
    db.add(article)
    db.commit()
    return RedirectResponse(f"/agent/kb/{article.id}", status_code=303)


@router.get("/{article_id}")
def kb_edit(
    request: Request,
    article_id: int,
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    article = db.get(KBArticle, article_id)
    if not article:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("agent/kb_form.html", ctx(request, article=article))


@router.post("/{article_id}/update")
def kb_update(
    request: Request,
    article_id: int,
    title: str = Form(...),
    category: str = Form("general"),
    summary: str = Form(...),
    body: str = Form(...),
    keywords: str = Form(""),
    published: str = Form(""),
    user: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    article = db.get(KBArticle, article_id)
    if not article:
        raise HTTPException(status_code=404)
    article.title = title.strip()
    article.category = category.strip() or "general"
    article.summary = summary.strip()
    article.body = body.strip()
    article.keywords = keywords.strip()
    article.published = bool(published)
    db.commit()
    return RedirectResponse(f"/agent/kb/{article.id}", status_code=303)
