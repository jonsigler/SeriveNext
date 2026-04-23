"""
Agentic AI for ticket triage and autonomous resolution.

Two providers, both FOSS-friendly:

* ``rule`` - deterministic keyword + TF-IDF-ish lexical matching against the
  knowledge base. Ships out of the box with zero external dependencies so the
  platform is useful even on an air-gapped machine.
* ``openai`` - talks to any OpenAI-compatible endpoint (Ollama, LM Studio,
  vLLM, llama.cpp server). Lets you plug in local Llama/Mistral/Qwen models.

The agent returns a :class:`TriageResult`. The caller decides, based on
``confidence`` vs ``AI_AUTO_RESOLVE_THRESHOLD``, whether to auto-resolve.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import KBArticle, Ticket, TicketCategory, TicketPriority


@dataclass
class TriageResult:
    category: TicketCategory
    priority: TicketPriority
    confidence: float  # 0..1 - how confident we are this is solvable automatically
    suggestion: str  # the proposed response / resolution
    matched_articles: list[KBArticle] = field(default_factory=list)
    can_auto_resolve: bool = False


# --- Heuristics ---------------------------------------------------------------

_CATEGORY_KEYWORDS: dict[TicketCategory, list[str]] = {
    TicketCategory.ACCESS: [
        "password", "reset", "locked out", "lockout", "mfa", "2fa", "sso", "sign in",
        "can't log in", "cannot log in", "account", "unlock", "permissions", "access denied",
    ],
    TicketCategory.HARDWARE: [
        "laptop", "desktop", "monitor", "screen", "keyboard", "mouse", "printer",
        "broken", "cracked", "battery", "charger", "dock", "webcam", "headset",
    ],
    TicketCategory.SOFTWARE: [
        "install", "uninstall", "crash", "error", "update", "license", "excel",
        "word", "outlook", "teams", "slack", "chrome", "edge", "vpn client",
    ],
    TicketCategory.NETWORK: [
        "wifi", "wi-fi", "internet", "network", "connection", "ethernet", "dns",
        "slow", "disconnected", "vpn", "firewall",
    ],
    TicketCategory.EMAIL: ["email", "mailbox", "outlook", "calendar", "meeting invite", "distribution list"],
    TicketCategory.PHONE: ["phone", "voicemail", "teams call", "voip", "sip"],
    TicketCategory.FACILITIES: ["desk", "chair", "badge", "door", "hvac", "lights", "building"],
    TicketCategory.SECURITY: [
        "phishing", "suspicious", "malware", "virus", "hacked", "breach",
        "ransomware", "leak",
    ],
    TicketCategory.REQUEST: ["request", "new laptop", "new hire", "onboarding", "need access to"],
}

_P1_SIGNALS = ("outage", "entire", "everyone", "production down", "can't work", "whole office", "breach", "ransomware")
_P2_SIGNALS = ("urgent", "asap", "blocker", "blocking", "multiple users", "team can't")
_P4_SIGNALS = ("when you have time", "nice to have", "fyi", "low priority", "whenever")


def _classify_category(text: str) -> tuple[TicketCategory, float]:
    t = text.lower()
    best = (TicketCategory.OTHER, 0)
    for cat, kws in _CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in t)
        if hits > best[1]:
            best = (cat, hits)
    # confidence from 0 to 0.6 contributed by category match
    conf = min(0.6, best[1] * 0.2)
    return best[0], conf


def _classify_priority(text: str) -> TicketPriority:
    t = text.lower()
    if any(s in t for s in _P1_SIGNALS):
        return TicketPriority.P1
    if any(s in t for s in _P2_SIGNALS):
        return TicketPriority.P2
    if any(s in t for s in _P4_SIGNALS):
        return TicketPriority.P4
    return TicketPriority.P3


# --- Lexical KB search --------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _score_article(article: KBArticle, query_tokens: set[str]) -> float:
    doc = f"{article.title} {article.summary} {article.keywords} {article.body}"
    doc_tokens = set(_tokenize(doc))
    if not doc_tokens:
        return 0.0
    overlap = query_tokens & doc_tokens
    if not overlap:
        return 0.0
    # Jaccard-ish, with extra weight for title hits.
    title_tokens = set(_tokenize(article.title))
    title_bonus = len(query_tokens & title_tokens) * 0.15
    base = len(overlap) / math.sqrt(len(query_tokens) * len(doc_tokens))
    return base + title_bonus


def find_matching_articles(db: Session, text: str, limit: int = 3) -> list[tuple[KBArticle, float]]:
    tokens = set(_tokenize(text))
    if not tokens:
        return []
    articles = db.scalars(select(KBArticle).where(KBArticle.published.is_(True))).all()
    scored = [(a, _score_article(a, tokens)) for a in articles]
    scored = [s for s in scored if s[1] > 0]
    scored.sort(key=lambda s: s[1], reverse=True)
    return scored[:limit]


# --- Rule-based provider ------------------------------------------------------

def _rule_triage(db: Session, ticket: Ticket) -> TriageResult:
    text = f"{ticket.subject}\n{ticket.description}"
    category, cat_conf = _classify_category(text)
    priority = _classify_priority(text)
    matches = find_matching_articles(db, text, limit=3)

    best_kb_score = matches[0][1] if matches else 0.0
    kb_conf = min(0.5, best_kb_score)  # cap KB contribution
    confidence = round(min(0.99, cat_conf + kb_conf), 2)

    if matches:
        top = matches[0][0]
        suggestion_lines = [
            f"Based on the description, this looks like a **{category.value}** issue.",
            "",
            f"The closest knowledge base match is **KB-{top.id}: {top.title}**.",
            "",
            top.summary,
            "",
            "Steps that usually resolve this:",
            top.body,
        ]
        if len(matches) > 1:
            suggestion_lines.append("")
            suggestion_lines.append("Related articles:")
            for art, _ in matches[1:]:
                suggestion_lines.append(f"- KB-{art.id}: {art.title}")
        suggestion = "\n".join(suggestion_lines)
    else:
        suggestion = (
            f"Classified as **{category.value}**, priority **{priority.value}**. "
            "No close knowledge base match. An agent will review."
        )

    can_auto_resolve = confidence >= get_settings().ai_auto_resolve_threshold and bool(matches)
    return TriageResult(
        category=category,
        priority=priority,
        confidence=confidence,
        suggestion=suggestion,
        matched_articles=[m[0] for m in matches],
        can_auto_resolve=can_auto_resolve,
    )


# --- LLM-backed provider ------------------------------------------------------

_SYSTEM_PROMPT = """You are an IT service desk triage assistant.

Return STRICT JSON ONLY (no code fences, no prose) with this shape:
{
  "category": one of ["access","hardware","software","network","email","phone","facilities","security","request","other"],
  "priority": one of ["p1","p2","p3","p4"],
  "confidence": number between 0 and 1 indicating how confident you are the
                matched knowledge base article solves this ticket end to end,
  "can_auto_resolve": boolean (true ONLY if you are highly confident the KB
                      article fully resolves the user's issue without any
                      human action),
  "suggestion": markdown text - a concise response the agent can send to the
                user, citing the KB article(s) by their KB-<id> identifiers
                when relevant
}
"""


def _llm_triage(db: Session, ticket: Ticket) -> TriageResult:
    settings = get_settings()
    text = f"{ticket.subject}\n{ticket.description}"
    matches = find_matching_articles(db, text, limit=5)
    kb_context = "\n\n".join(
        f"KB-{a.id} [{a.category}] {a.title}\nSummary: {a.summary}\nBody:\n{a.body}"
        for a, _ in matches
    ) or "(no knowledge base articles matched lexically)"

    user_msg = (
        f"Ticket subject: {ticket.subject}\n\n"
        f"Ticket description:\n{ticket.description}\n\n"
        f"Candidate knowledge base articles (pre-retrieved):\n{kb_context}\n\n"
        "Respond with the JSON described in the system prompt."
    )
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}"},
                json={
                    "model": settings.ai_model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.2,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        data = _extract_json(content)
        category = TicketCategory(data.get("category", "other"))
        priority = TicketPriority(data.get("priority", "p3"))
        confidence = float(data.get("confidence", 0.0))
        suggestion = str(data.get("suggestion", "")).strip() or "(no suggestion)"
        can_auto = bool(data.get("can_auto_resolve", False)) and confidence >= settings.ai_auto_resolve_threshold
        return TriageResult(
            category=category,
            priority=priority,
            confidence=round(min(max(confidence, 0.0), 0.99), 2),
            suggestion=suggestion,
            matched_articles=[m[0] for m in matches],
            can_auto_resolve=can_auto,
        )
    except Exception as e:  # noqa: BLE001 - we want a safe fallback always
        # Never let a flaky LLM break ticket creation. Fall back to rules.
        rule_result = _rule_triage(db, ticket)
        rule_result.suggestion = (
            f"_(LLM provider unavailable: {type(e).__name__}; used rule-based fallback)_\n\n"
            + rule_result.suggestion
        )
        return rule_result


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip accidental code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
    # Grab the first {...} block if there's any surrounding prose.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


# --- Public API ---------------------------------------------------------------

def triage(db: Session, ticket: Ticket) -> TriageResult:
    settings = get_settings()
    if settings.ai_provider == "openai":
        return _llm_triage(db, ticket)
    return _rule_triage(db, ticket)


def apply_triage(db: Session, ticket: Ticket, result: TriageResult) -> None:
    """Persist triage result onto the ticket and log it."""
    from app.models import TicketEvent, TicketStatus

    ticket.category = result.category
    ticket.priority = result.priority
    ticket.ai_triaged = True
    ticket.ai_confidence = result.confidence
    ticket.ai_suggestion = result.suggestion
    if ticket.status == TicketStatus.NEW:
        ticket.status = TicketStatus.TRIAGED

    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            author_id=None,
            kind="ai",
            is_internal=False,
            body=(
                f"**AI triage** — category: `{result.category.value}`, "
                f"priority: `{result.priority.value}`, confidence: `{result.confidence}`.\n\n"
                f"{result.suggestion}"
            ),
        )
    )


def maybe_auto_resolve(db: Session, ticket: Ticket, result: TriageResult) -> bool:
    """If the triage result is confident, mark the ticket resolved autonomously."""
    from app.models import TicketEvent, TicketStatus

    if not result.can_auto_resolve:
        return False
    ticket.ai_auto_resolved = True
    ticket.resolution = (
        f"Autonomously resolved by AI agent (confidence {result.confidence}).\n\n"
        f"{result.suggestion}"
    )
    ticket.status = TicketStatus.RESOLVED
    from datetime import datetime as _dt
    ticket.resolved_at = _dt.utcnow()
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            author_id=None,
            kind="ai",
            body="Ticket autonomously resolved by AI. Requester can reopen if this didn't help.",
        )
    )
    return True
