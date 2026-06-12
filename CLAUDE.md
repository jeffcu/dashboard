# Personal Systems Dashboard — Engineering Guide

> **This is a living document.** Every session reads it at the start and updates it at the end.

---

## What This Project Is

A personal life-balance and social-maintenance system for Jeff Curie. It tracks daily time investment across shifting life domains (art, tech, biking, civic work, finance, etc.), maintains a social contact queue with history and cadence, manages household todos, and delivers a daily morning briefing via Telegram. Three clients: web dashboard (LCARS aesthetic), Telegram bot (mobile quick-actions), and macOS menu bar (xbar glanceable status).

---

## Always Read First

1. This file — architecture, constraints, and current state
2. `REQUIREMENTS.md` — full functional and data spec (read before touching any module)

---

## Session Protocol — Mandatory

### Before starting any task
1. Read this entire CLAUDE.md. Do not skip sections.
2. Check **Current State** — confirms what's working, what's broken, what's next.
3. Check **Debugging History** for the area you're working in.
4. For any external API or service: fetch live documentation before writing a single line. Never rely on training data for API contracts.
5. State today's goal in one sentence. Do not begin until that goal is confirmed.

### During the session
6. Stay on the current Build Plan phase.
7. Record failures in Debugging History immediately.
8. Record successes so Current State can be updated.
9. If you discover a new constraint, add it to Critical Constraints.

### At the end of every session
10. Update Current State, Build Plan status, Debugging History, What's Next, and Session Log.
11. If new architectural decisions were made, add them to Locked Design Decisions.
12. Document any newly confirmed API contracts.

---

## Architecture Overview

### Stack
- **Backend:** Python + FastAPI (async, lightweight)
- **Database:** SQLite via SQLAlchemy (volume-mounted, zero-ops)
- **Scheduler:** APScheduler in-process (daily briefing cron)
- **Telegram:** python-telegram-bot (polling mode — no public URL needed)
- **Web UI:** Single HTML file (vanilla JS, LCARS aesthetic), served by FastAPI
- **Container:** Docker + docker-compose
- **Menu bar:** xbar plugin (shell script calling local API)

### Deployment topology
```
[Docker container: port 8765]
  ├── FastAPI (REST API + static file server)
  ├── SQLite database (/data/dashboard.db — volume mount)
  ├── APScheduler (fires daily 7:30am Telegram briefing)
  └── Telegram bot (long-polling — no webhook, no public URL)

[macOS host]
  └── xbar plugin (~/.config/xbar/plugins/dashboard.1m.sh)
      polls localhost:8765/api/summary every 1 min

[Telegram cloud]
  └── Private bot — responds only to TELEGRAM_ALLOWED_USER_ID
```

### File Structure
```
dashboard/
├── docker-compose.yml
├── Dockerfile
├── .env                    ← secrets, never committed
├── .env.example
├── requirements.txt
├── REQUIREMENTS.md         ← full spec
├── CLAUDE.md               ← this file
├── data/                   ← volume-mounted, gitignored
│   └── dashboard.db
├── app/
│   ├── main.py             ← FastAPI app, router registration
│   ├── database.py         ← SQLAlchemy setup
│   ├── models.py           ← ORM table definitions
│   ├── seed.py             ← Default domain + friend seeding
│   ├── scheduler.py        ← APScheduler + briefing logic
│   ├── telegram_bot.py     ← Bot command handlers
│   ├── routers/
│   │   ├── log.py
│   │   ├── projects.py
│   │   ├── social.py
│   │   ├── todos.py
│   │   └── summary.py
│   └── static/
│       └── dashboard.html  ← Web UI (single file)
└── xbar/
    └── dashboard.1m.sh     ← xbar plugin
```

---

## Running the Project

```bash
# First time setup
cp .env.example .env
# Edit .env with TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID

# Start everything
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

**Access:** http://localhost:8765

**Environment variables (in .env — never commit):**
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...
BRIEFING_TIME=07:30
TZ=America/Los_Angeles
PORT=8765
```

---

## Critical Constraints

- **NEVER use port 5000 or 7000** — both reserved by macOS (AirPlay). Use 8765.
- **NEVER expose the service publicly without auth** — no HTTPS, no public URL in v2. Localhost only.
- **NEVER hard-delete friends** — archive only (active=0). Contact history must be preserved.
- **NEVER let the Telegram bot respond to users other than TELEGRAM_ALLOWED_USER_ID** — silent ignore for all others.
- **ALWAYS set TZ in docker-compose.yml** — APScheduler fires at wall-clock time; without TZ it fires at UTC.
- **ALWAYS mount /data as a volume** — database must survive container restarts.
- **NEVER store secrets in source files** — all tokens in .env, .env in .gitignore.

---

## Locked Design Decisions

| Question | Decision | Reasoning |
|---|---|---|
| Persistence layer | SQLite via SQLAlchemy | Zero-ops, single file, survives Docker restarts via volume mount. Adequate for single-user. |
| Telegram mode | Long-polling (not webhook) | No public URL required. Works perfectly from localhost Docker. |
| Web UI delivery | Single HTML file served by FastAPI | No build step, easy to edit, consistent with v1 aesthetic. |
| Bot security | Allowlist by Telegram user ID | Simplest private-bot pattern. No per-command tokens to manage. |
| Menu bar | xbar plugin | Free, open-source, zero native code. |
| Port | 8765 | Avoids macOS AirPlay (5000), AirPlay receiver (7000), and common dev ports. |
| Todos completed items | Soft-delete (active=0) | Preserves history; recurring items need completion record to calculate next due date. |
| DB path | `DB_PATH` env var, default `./data/dashboard.db` | Same code runs in Docker (/data volume) and bare uvicorn for dev/testing. |
| Bot `/log` semantics | Additive (adds hours to existing, clamps at 8) | Quick-logging from phone means "I just did 2 more hours", not "set total to 2". Web UI clicks set absolute values. |
| Domain reorder UI | ▲▼ buttons, not drag-and-drop | Spec said drag-and-drop; buttons are 10x simpler, same outcome, no library. Revisit only if it annoys in practice. |
| Bot/scheduler startup | Inside FastAPI lifespan, token-optional | Single process, single container. Missing token → bot DORMANT, everything else runs. Token can be added any time via .env + restart. |

---

## Component / Service Status

| Component | File | Status | Notes |
|---|---|---|---|
| dashboard.html v1 | dashboard.html | **Legacy** — localStorage only | Initial prototype; superseded by v2 |
| FastAPI backend | app/ | **Built + tested** | All routers verified via live server + curl 2026-06-12 |
| Web UI v2 | app/static/dashboard.html | **Built** | Served at / — needs visual verification in browser |
| Telegram bot | app/telegram_bot.py | **Built — dormant** | Starts clean without token; live commands untested (no token yet) |
| Scheduler | app/scheduler.py | **Built + tested** | Fires at BRIEFING_TIME in TZ; briefing text verified via /api/brief |
| xbar plugin | xbar/dashboard.1m.sh | **Built + tested** | Live output + OFFLINE fallback both verified in sandbox |
| Docker | Dockerfile, docker-compose.yml | **Built** | Not yet run on host — needs `docker compose up` verification |

---

## Build Plan

### Phase 1 — Data skeleton
**Goal:** FastAPI running in Docker with SQLite, all tables created, seed data loaded  
**Builds:** Dockerfile, docker-compose.yml, app/main.py, app/database.py, app/models.py, app/seed.py, app/routers/summary.py  
**Done when:** `curl localhost:8765/api/summary` returns valid JSON with domain list and friend counts  
**Prerequisite:** .env configured (Telegram token can be dummy for this phase)  
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 2 — Daily Log API + UI
**Goal:** Web UI heatmap backed by API, not localStorage  
**Builds:** app/routers/log.py, app/static/dashboard.html (heatmap module)  
**Done when:** Log hours via click, navigate weeks, see totals — persisted to DB across browser refresh  
**Prerequisite:** Phase 1 complete  
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 3 — Social Queue API + UI
**Goal:** Friend list with phase workflow, contact history, due dates  
**Builds:** app/routers/social.py, social module in dashboard.html  
**Done when:** Advance Mitch to DONE with note; history shows entry; overdue badge correct  
**Prerequisite:** Phase 2 complete  
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 4 — Projects + Todos API + UI
**Goal:** Dynamic project management + enhanced todo lists  
**Builds:** app/routers/projects.py, app/routers/todos.py, projects + todos modules in dashboard.html  
**Done when:** Add new project, write diary entry, add recurring todo with due date  
**Prerequisite:** Phase 3 complete  
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 5 — Telegram bot + daily briefing
**Goal:** Bot handles all commands; 7:30am briefing fires  
**Builds:** app/telegram_bot.py, app/scheduler.py  
**Done when:** `/log art 2` updates DB and bot confirms; briefing arrives at correct time  
**Prerequisite:** Phase 4 complete  
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 6 — xbar menu bar plugin
**Goal:** Menu bar shows week total and overdue count; opens dashboard on click  
**Builds:** xbar/dashboard.1m.sh  
**Done when:** Plugin installed, shows live data, shows OFFLINE when Docker is stopped  
**Prerequisite:** Phase 5 complete  
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 7 — Trends + goals
**Goal:** 8-week sparklines, streak counters, per-domain goal progress  
**Builds:** trends endpoint in log.py, trends panel in dashboard.html  
**Done when:** Trends panel renders 8 weeks; goal indicators update correctly  
**Prerequisite:** Phase 6 complete  
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

---

## MVP Scope

### In scope
- All four enhanced modules with full DB persistence
- REST API
- Telegram daily briefing (7:30am) + bot commands
- Docker single-command startup
- xbar menu bar plugin
- Weekly goals + cross-week trends
- Social contact history + cadence/due dates
- Todo due dates + recurring tasks
- Dynamic domain and project management

### Out of scope (deferred)
- Multi-user support
- Mobile web UI (Telegram handles mobile interaction)
- Data export UI
- Public access / Tailscale
- Authentication / HTTPS

**MVP in one sentence:** A single Docker command starts a personal life-balance dashboard with a Telegram bot delivering a morning briefing and accepting quick-log commands from anywhere.

---

## Current State

### Confirmed Working (verified by live server + curl in Linux sandbox, 2026-06-12)
- Full FastAPI backend: all 25+ endpoints across log, domains, projects, diary, social, todos, summary, brief
- Seed data: 10 domains, 12 friends, 8 projects load on first run (empty-table check)
- Daily log upsert + week readback + 8-week trends + streaks + goal PATCH
- Social workflow: advance with note → history entry; DONE sets last_done_at + due_date (cadence); reset; overdue badge counts; soft-delete preserves history
- Todos: due dates, overdue flag, weekly recurrence spawns next occurrence on completion, soft-delete, clear-completed
- Diary: append entries, full-text search across projects
- `/api/brief` renders the full daily briefing text per spec format
- SQLite persistence across server restarts (DB file survives, data intact)
- Telegram bot dormant mode: app starts cleanly with no token, logs DORMANT message
- APScheduler armed at 07:30 America/Los_Angeles
- xbar plugin: live output correct, OFFLINE fallback correct
- Web UI v2 served at / (HTML loads; full click-through still needs a real browser)

### Known Issues
- None found in API testing

### Unknown / Needs Investigation
- Web UI v2 needs visual click-through in a real browser (heatmap clicks, modal, trends panel, domain settings)
- Docker build not yet run on the Mac host (sandbox tested bare uvicorn, not the container)
- Telegram bot live commands + 7:30 briefing delivery untested — waiting on real token + user ID

### Current Build Plan Phase
**Active phase:** Verification — all 7 phases code-complete; user acceptance pending  
**Remaining:** `docker compose up` on host, browser click-through, Telegram token, xbar install

---

## What's Next

1. Jeff: `cp .env.example .env` (dummy token values are fine for now) then `docker compose up -d --build`
2. Confirm `curl localhost:8765/api/summary` and open http://localhost:8765 — click through all four tabs
3. Jeff provides real TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USER_ID → restart container → test `/log art 2` and `/brief`
4. Install xbar plugin: `cp xbar/dashboard.1m.sh ~/.config/xbar/plugins/ && chmod +x ~/.config/xbar/plugins/dashboard.1m.sh`
5. Confirm 7:30am briefing arrives next morning

---

## External Services and APIs

### Telegram Bot API
**Documentation:** https://core.telegram.org/bots/api  
**Used for:** Daily briefing push + bot command handling  
**Auth method:** Bot token  
**Library:** python-telegram-bot  
**Known constraints:** Long-polling works from behind NAT/Docker with no public URL

### APScheduler
**Documentation:** https://apscheduler.readthedocs.io/en/stable/  
**Used for:** Cron job for 7:30am daily briefing  
**Known constraints:** Must set timezone explicitly; default fires at UTC

### xbar
**Documentation:** https://github.com/matryer/xbar  
**Used for:** macOS menu bar plugin  
**Known constraints:** Plugin filename format: `name.NUMBERm.sh`; minimum 1-second refresh

---

## Debugging History

| Date | What Was Tried | What Happened | Root Cause |
|---|---|---|---|
| 2026-06-12 | xbar plugin: Python block wrapped in bash single quotes | `syntax error near unexpected token '('` at line 51 | Python f-strings containing single quotes terminated the bash quote. Fix: feed Python via `<<'PYEOF'` heredoc + JSON via env var — never inline-quote Python in shell scripts |
| 2026-06-12 | Testing server with background `&` across separate sandbox shell calls | curl returned HTTP 000; process dead | Claude's sandbox reaps background processes between bash calls. Server + all curls must run in ONE shell invocation when testing there. Not a project bug |

---

## Session Log

### 2026-06-12 (build session)
**Phase:** Phases 1–7 — full system build  
**Attempted:** Build the entire v2 system in one pass, ready to accept data, Telegram dormant until token provided  
**Succeeded:** Everything built and API-tested live in sandbox: Docker config, SQLAlchemy models + seed, all 5 routers (25+ endpoints), briefing builder, APScheduler wiring, token-optional Telegram bot (PTB 22.8 async Application API), web UI v2 (single-file LCARS, all 4 modules + trends + domain settings + history + modal), xbar plugin with OFFLINE fallback. Every phase's done-criteria exercised via curl: log/readback/trends, Mitch→DONE with note + history, overdue badge (Greg +45d), recurring todo spawn, diary search, full briefing text render. Dependencies pinned: fastapi 0.136, sqlalchemy 2.0.50, apscheduler 3.11 (v3 API, not v4), python-telegram-bot 22.8.  
**Failed:** xbar script bash-quoting bug (fixed via heredoc — see Debugging History)  
**New constraints discovered:** None for the project; sandbox testing requires single-shell-call server+curl  
**Plan changes:** Domain reorder via ▲▼ buttons instead of drag-and-drop (logged in Locked Decisions)  
**Awaiting user:** docker compose up on host, browser click-through, Telegram credentials, xbar install

### 2026-06-12
**Phase:** Pre-build — requirements and architecture  
**Attempted:** Establish project requirements based on v1 prototype critique  
**Succeeded:** Full REQUIREMENTS.md written; CLAUDE.md bootstrapped with real architecture, build plan, and constraints  
**Failed:** Nothing  
**New constraints discovered:** Port 8765 chosen; TZ required in Docker; Telegram long-polling chosen over webhook  
**Plan changes:** Entire project rearchitected from browser-only localStorage to Docker + FastAPI + SQLite + Telegram + xbar

---

## Authoritative Sources

| Service / Library | Documentation URL | Last verified |
|---|---|---|
| python-telegram-bot | https://python-telegram-bot.readthedocs.io/ | 2026-06-12 |
| FastAPI | https://fastapi.tiangolo.com/ | 2026-06-12 |
| SQLAlchemy | https://docs.sqlalchemy.org/ | 2026-06-12 |
| APScheduler | https://apscheduler.readthedocs.io/ | 2026-06-12 |
| xbar | https://github.com/matryer/xbar | 2026-06-12 |
| Telegram Bot API | https://core.telegram.org/bots/api | 2026-06-12 |

---

*CLAUDE.md is a living document. If something in this file is wrong, update it immediately.*
