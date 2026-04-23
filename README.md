# SeriveNext

**Open-source IT service management** — a ServiceNow/Salesforce-inspired ITSM
platform built entirely from free and open-source components. Cases, a CMDB,
knowledge base, and an **agentic AI** that triages and autonomously resolves
routine tickets.

## Features

- **Case / incident management** – full lifecycle: new → triaged → in progress
  → pending → resolved → closed, with priority, category, source, assignee,
  internal notes, and a unified activity stream.
- **CMDB (Configuration Management Database)** – track servers, workstations,
  laptops, network devices, printers, applications, services, and databases.
  Link tickets to affected CIs so you can see every incident against an asset.
- **Knowledge Base** – agents publish articles; end users can search them from
  the portal; the AI agent uses them as grounding for its suggestions.
- **End-user portal** – clean self-service UI where employees submit tickets,
  browse KB, and follow up on their cases.
- **Agent console** – dashboard with SLA-relevant counters, filterable queue,
  full ticket workspace, CMDB management, KB authoring.
- **Agentic AI** – every new ticket is auto-triaged:
  - classifies category + priority,
  - retrieves the most relevant KB articles,
  - drafts a suggested response,
  - and — when its confidence clears the configured threshold — **autonomously
    resolves the ticket** and lets the requester reopen it if the answer misses.
  The AI layer has two providers: a deterministic rule engine that ships
  out-of-the-box with zero external dependencies, and an OpenAI-compatible
  HTTP client that transparently talks to any local LLM (Ollama, LM Studio,
  llama.cpp server, vLLM).
- **JSON API** for integrations at `/api/v1/*` (OpenAPI docs at `/docs`).
- **Role-based access control** – `end_user`, `agent`, `admin`.

## Stack (all FOSS)

| Layer                | Choice                                                  | License       |
|----------------------|---------------------------------------------------------|---------------|
| Web framework        | FastAPI                                                 | MIT           |
| ORM                  | SQLAlchemy 2.0                                          | MIT           |
| Database             | SQLite (default) / PostgreSQL (drop-in)                 | Public domain / PostgreSQL |
| Templates            | Jinja2                                                  | BSD           |
| Frontend interactivity | HTMX + Alpine.js                                      | BSD / MIT     |
| Styling              | Tailwind CSS (CDN)                                      | MIT           |
| Auth                 | passlib + bcrypt + itsdangerous sessions                | BSD           |
| HTTP client (LLM)    | httpx                                                   | BSD           |
| ASGI server          | uvicorn                                                 | BSD           |
| LLM (optional)       | Any OpenAI-compatible local server: Ollama, LM Studio, llama.cpp | Apache 2.0 / MIT |

## Quick start

```bash
./run.sh seed      # create the DB + load demo data
./run.sh serve     # start on http://localhost:8000
```

Demo logins (created by `seed`):

| Role       | Email                          | Password   |
|------------|--------------------------------|------------|
| Admin      | `admin@serivenext.local`       | `admin123` |
| Agent      | `agent@serivenext.local`       | `agent123` |
| End user   | `user@serivenext.local`        | `user1234` |

Then:

1. Sign in as the **end user** and submit a ticket like "I forgot my password"
   — watch the AI agent auto-resolve it using the seeded KB article.
2. Sign in as the **agent** to see the queue, work cases, manage CIs, and
   author KB articles.

## Using a real LLM (optional)

SeriveNext is 100% functional without any LLM thanks to the built-in
rule-based agent. To plug in a local model:

1. Run [Ollama](https://ollama.com) (Apache-2.0): `ollama pull llama3.1:8b && ollama serve`
2. Copy `.env.example` to `.env` and set:
   ```
   AI_PROVIDER=openai
   AI_BASE_URL=http://localhost:11434/v1
   AI_API_KEY=ollama
   AI_MODEL=llama3.1:8b
   ```
3. Restart: `./run.sh serve`.

Any OpenAI-compatible endpoint works (LM Studio, vLLM, llama.cpp server, etc.).

## Deploying (Fly.io, Docker, compose, VPS)

The repo ships with a `Dockerfile`, a `docker-compose.yml`, and a `fly.toml` so
you can put SeriveNext on the internet without extra plumbing.

### Fly.io — free tier, HTTPS URL, ~2 minutes

```bash
# one-time
curl -L https://fly.io/install.sh | sh
fly auth signup                   # or: fly auth login

# from inside the repo
fly launch --copy-config --no-deploy
fly volumes create serivenext_data --size 1
fly secrets set SECRET_KEY="$(openssl rand -hex 32)"
fly deploy
fly open
```

You get a URL like `https://<your-app>.fly.dev`. The SQLite DB lives on a 1 GB
persistent volume so deploys don't wipe data. On first boot the demo seed
users are created; **change their passwords immediately** (or set
`SEED_ON_START=0` in `fly.toml` and register users fresh).

### Docker / docker-compose — any host that runs containers

```bash
export SECRET_KEY="$(openssl rand -hex 32)"
docker compose up -d
# → http://<host>:8000
```

The compose file mounts a named volume `serivenext_data` so the SQLite DB
survives restarts. Drop it behind a reverse proxy (Caddy, nginx, Traefik) for
HTTPS.

### VPS (systemd)

Build the image on the box (`docker build -t serivenext .`), then run it as a
systemd-managed container — or skip Docker entirely and run `uvicorn` under a
systemd unit. Either works; the Dockerfile encodes the right defaults either
way.

## Switching to PostgreSQL

Set `DATABASE_URL` in `.env`, e.g.:

```
DATABASE_URL=postgresql+psycopg://serivenext:secret@localhost:5432/serivenext
```

## Project layout

```
app/
  config.py          # pydantic settings from env
  database.py        # SQLAlchemy engine + Base
  security.py        # auth dependencies, password hashing
  main.py            # FastAPI app, middleware, routers
  models/            # User, Ticket, CMDB, KB, events
  routers/           # auth, portal, agent, cmdb, kb, api
  services/
    ticket_service.py  # ticket lifecycle + events
    ai_agent.py        # triage + autonomous resolution
  templates/         # Jinja2 (portal/, agent/)
  static/            # CSS
scripts/seed.py      # demo users, KB, CIs, tickets
run.sh               # dev launcher
requirements.txt
```

## JSON API

- `POST /api/v1/tickets` — create a ticket (triggers AI triage).
- `GET  /api/v1/tickets/{id}` — read a ticket (requester or agent).
- `POST /api/v1/tickets/{id}/retriage` — re-run AI triage (agent only).

Interactive Swagger UI: http://localhost:8000/docs.

## Compared with ServiceNow / Salesforce

| Capability                              | ServiceNow ITSM | SeriveNext |
|-----------------------------------------|-----------------|------------|
| Cases / incidents                       | ✅              | ✅         |
| CMDB with typed CIs                     | ✅              | ✅         |
| Service catalog                         | ✅              | 🟡 (KB + ticket) |
| Knowledge base                          | ✅              | ✅         |
| End-user portal                         | ✅              | ✅         |
| Agent workspace                         | ✅              | ✅         |
| Virtual Agent / AI triage               | ✅ (paid add-on)| ✅ (built-in, FOSS) |
| Autonomous resolution                   | ✅ (Now Assist) | ✅         |
| Role-based access                       | ✅              | ✅ (3 roles) |
| Multi-tenant, change mgmt, workflows    | ✅              | ❌ (not in scope) |
| Cost                                    | $$$             | $0         |
| Vendor lock-in                          | Total           | None — all FOSS |
