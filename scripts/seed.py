"""Seed the database with demo users, KB articles, and CMDB assets.

Run with:  python -m scripts.seed
"""

from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import (
    CIType,
    ConfigurationItem,
    KBArticle,
    Role,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketSource,
    User,
)
from app.security import hash_password
from app.services import ai_agent, ticket_service


KB_SEEDS: list[dict] = [
    {
        "title": "How to reset your password",
        "category": "access",
        "summary": "Self-service password reset using the corporate SSO portal.",
        "keywords": "password reset forgot locked account sso login sign in",
        "body": (
            "If you forgot your password or can't sign in, you can reset it yourself:\n\n"
            "1. Visit https://sso.example.com/reset\n"
            "2. Enter your corporate email address\n"
            "3. Click the one-time code we email you (expires in 10 minutes)\n"
            "4. Choose a new password with at least 12 characters\n\n"
            "If your account is locked, wait 15 minutes and try again. If it still fails, "
            "open a ticket and an agent will unlock it."
        ),
    },
    {
        "title": "Fix Wi-Fi connectivity on a corporate laptop",
        "category": "network",
        "summary": "Steps to restore Wi-Fi when your laptop can't connect to the office network.",
        "keywords": "wifi wi-fi wireless network internet disconnected slow",
        "body": (
            "1. Toggle Wi-Fi off and back on from the system tray\n"
            "2. Forget the 'Corp-Secure' network and reconnect using your corporate SSO\n"
            "3. Restart the laptop\n"
            "4. If still failing, plug in to a wired port and run `ipconfig /all` (Windows) or "
            "`ifconfig` (macOS) and send the output to the service desk.\n"
        ),
    },
    {
        "title": "Request new software installation",
        "category": "software",
        "summary": "How to request approved software via the self-service catalog.",
        "keywords": "install software application request license",
        "body": (
            "Most approved software is available from the Software Center. For items not listed:\n\n"
            "1. Open a ticket and choose category 'software'\n"
            "2. Include the exact product name, version, and business justification\n"
            "3. Your manager will be emailed for approval\n"
            "4. Approved installs are pushed silently within one business day."
        ),
    },
    {
        "title": "Report a suspected phishing email",
        "category": "security",
        "summary": "How to safely report phishing or suspicious emails.",
        "keywords": "phishing suspicious email malware security breach",
        "body": (
            "Do NOT click links or open attachments.\n\n"
            "Use the 'Report Phishing' button in Outlook, or forward the email as an "
            "attachment to security@example.com. The Security team will investigate and "
            "respond within 4 hours."
        ),
    },
    {
        "title": "Outlook won't send or receive mail",
        "category": "email",
        "summary": "Common fixes when Outlook hangs or shows disconnected.",
        "keywords": "outlook email mailbox disconnected send receive",
        "body": (
            "1. Check the bottom status bar - if it says 'Disconnected', click Send/Receive → Work Offline (to toggle it off)\n"
            "2. File → Account Settings → Repair\n"
            "3. Restart Outlook\n"
            "4. If the mailbox is near its size limit, archive old mail"
        ),
    },
    {
        "title": "Printer is offline or jobs stuck in queue",
        "category": "hardware",
        "summary": "How to clear a stuck print queue and reconnect to the printer.",
        "keywords": "printer print queue offline stuck paper jam",
        "body": (
            "1. Open Settings → Printers & scanners, open the queue, and cancel all jobs\n"
            "2. Right-click the printer → Remove device\n"
            "3. Re-add it from \\\\print01\\<printer-name>\n"
            "4. If the printer shows offline at the device itself, check for paper jams"
        ),
    },
    {
        "title": "New hire onboarding - first-day IT checklist",
        "category": "request",
        "summary": "What a new hire needs on day one: laptop, accounts, access.",
        "keywords": "onboarding new hire day one laptop account",
        "body": (
            "Managers should submit a new-hire request at least 5 business days before the start date. "
            "Include: legal name, job title, manager, start date, location, required software groups."
        ),
    },
    {
        "title": "VPN not connecting",
        "category": "network",
        "summary": "Resolve common VPN client failures.",
        "keywords": "vpn connect tunnel remote",
        "body": (
            "1. Ensure you're on a non-corporate network (VPN is blocked when inside the office)\n"
            "2. Update the VPN client to the latest version via Software Center\n"
            "3. Sign in with your corporate SSO credentials\n"
            "4. If the client hangs on 'Connecting', reboot and try again"
        ),
    },
]


CIS: list[dict] = [
    {"name": "LT-10234", "ci_type": CIType.LAPTOP, "asset_tag": "ASSET-10234", "manufacturer": "Dell", "model": "Latitude 7440", "os": "Windows 11", "serial_number": "DL7440-ABCD01"},
    {"name": "LT-10235", "ci_type": CIType.LAPTOP, "asset_tag": "ASSET-10235", "manufacturer": "Apple", "model": "MacBook Pro 14", "os": "macOS 14", "serial_number": "MBP14-XYZQ22"},
    {"name": "PRN-FLR2-A", "ci_type": CIType.PRINTER, "manufacturer": "HP", "model": "LaserJet Pro M479", "ip_address": "10.12.4.55", "location": "Floor 2"},
    {"name": "SRV-MAIL-01", "ci_type": CIType.SERVER, "manufacturer": "Dell", "model": "PowerEdge R650", "os": "Ubuntu 22.04", "ip_address": "10.0.1.10", "location": "DC-East"},
    {"name": "SVC-SSO", "ci_type": CIType.SERVICE, "description": "Corporate SSO service (Keycloak)"},
    {"name": "SVC-Email", "ci_type": CIType.SERVICE, "description": "Email service cluster"},
    {"name": "SW-Office365", "ci_type": CIType.APPLICATION, "description": "Microsoft 365 productivity suite"},
    {"name": "DB-Primary", "ci_type": CIType.DATABASE, "manufacturer": "PostgreSQL", "model": "16", "ip_address": "10.0.2.7"},
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        # --- users ---
        def upsert_user(email: str, name: str, role: Role, password: str, department: str | None = None) -> User:
            existing = db.scalar(select(User).where(User.email == email))
            if existing:
                return existing
            u = User(
                email=email,
                full_name=name,
                role=role,
                department=department,
                password_hash=hash_password(password),
            )
            db.add(u)
            db.flush()
            return u

        admin = upsert_user("admin@serivenext.local", "System Admin", Role.ADMIN, "admin123", "IT")
        agent1 = upsert_user("agent@serivenext.local", "Alex Agent", Role.AGENT, "agent123", "IT Service Desk")
        agent2 = upsert_user("agent2@serivenext.local", "Bailey Support", Role.AGENT, "agent123", "IT Service Desk")
        user1 = upsert_user("user@serivenext.local", "Jamie User", Role.END_USER, "user1234", "Marketing")
        user2 = upsert_user("taylor@serivenext.local", "Taylor Employee", Role.END_USER, "user1234", "Finance")

        # --- KB ---
        for k in KB_SEEDS:
            existing = db.scalar(select(KBArticle).where(KBArticle.title == k["title"]))
            if existing:
                continue
            db.add(KBArticle(**k, author_id=admin.id))

        # --- CIs ---
        ci_by_name: dict[str, ConfigurationItem] = {}
        for c in CIS:
            existing = db.scalar(select(ConfigurationItem).where(ConfigurationItem.name == c["name"]))
            if existing:
                ci_by_name[existing.name] = existing
                continue
            ci = ConfigurationItem(**c)
            if c["name"] == "LT-10234":
                ci.owner_id = user1.id
            if c["name"] == "LT-10235":
                ci.owner_id = user2.id
            db.add(ci)
            db.flush()
            ci_by_name[ci.name] = ci

        db.commit()

        # --- demo tickets (only if none exist) ---
        if (db.scalar(select(Ticket)) is None):
            samples = [
                {
                    "requester": user1,
                    "subject": "I forgot my password and can't log in",
                    "description": (
                        "Hi, I tried logging into my laptop this morning and my password doesn't work. "
                        "I think it expired over the weekend. Can you help me reset it?"
                    ),
                },
                {
                    "requester": user2,
                    "subject": "Wi-Fi keeps disconnecting on my MacBook",
                    "description": (
                        "My MacBook Pro keeps dropping off the Corp-Secure Wi-Fi every ~10 minutes. "
                        "Other people near me aren't having the problem. It started yesterday."
                    ),
                },
                {
                    "requester": user1,
                    "subject": "Received a weird email claiming to be from the CEO",
                    "description": (
                        "I got a phishing-looking email asking me to buy gift cards. Subject was "
                        "'URGENT - need your help'. I didn't click anything. What should I do?"
                    ),
                },
            ]
            for s in samples:
                t = ticket_service.create_ticket(
                    db,
                    requester=s["requester"],
                    subject=s["subject"],
                    description=s["description"],
                    source=TicketSource.PORTAL,
                    priority=TicketPriority.P3,
                    category=TicketCategory.OTHER,
                )
                result = ai_agent.triage(db, t)
                ai_agent.apply_triage(db, t, result)
                ai_agent.maybe_auto_resolve(db, t, result)
                db.commit()

        print("Seeded.")
        print("  Admin:    admin@serivenext.local / admin123")
        print("  Agent:    agent@serivenext.local / agent123")
        print("  End user: user@serivenext.local  / user1234")


if __name__ == "__main__":
    main()
