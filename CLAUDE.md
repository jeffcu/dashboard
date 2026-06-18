# Personal Systems Dashboard — Engineering Guide

> **This is a living document.** Every session reads it at the start and updates it at the end.

---

## What This Project Is

A personal life-balance and social-maintenance system for Jeff Curie. It tracks daily time investment across shifting life domains (art, tech, biking, civic work, finance, etc.), maintains a social contact queue with history and cadence, manages household todos, and delivers a daily morning briefing via Telegram. Three clients: web dashboard ("Workshop" aesthetic — warm paper, ink, burnt orange/teal), Telegram bot (mobile quick-actions), and macOS menu bar (xbar glanceable status).

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
- **Web UI:** Single HTML file (vanilla JS, Workshop aesthetic), served by FastAPI; `app/static/` is **volume-mounted** — HTML/CSS/JS changes are live on hard-refresh (Cmd+Shift+R), no rebuild needed
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
│   ├── briefing.py         ← Agenda engine (ONE source for TODAY, brief, Telegram)
│   ├── scheduler.py        ← APScheduler + briefing logic
│   ├── telegram_bot.py     ← Bot command handlers
│   ├── routers/
│   │   ├── log.py
│   │   ├── projects.py
│   │   ├── project_log.py  ← Project-level time tracking + domain rollup
│   │   ├── goals.py        ← /api/goals underperformer engine
│   │   ├── social.py
│   │   ├── todos.py
│   │   └── summary.py
│   └── static/
│       └── dashboard.html  ← Web UI (single file, volume-mounted = live on refresh)
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

# Rebuild after any Python/backend change
docker compose up -d --build

# HTML/CSS/JS changes: just Cmd+Shift+R in browser (no rebuild needed)

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
- **git operations MUST run on the host Mac** — sandbox leaves immortal `.git/index.lock` files in the Dropbox-mounted folder.
- **SQLite writes from sandbox require `PRAGMA journal_mode=MEMORY`** — mount can't delete the journal file.
- **Python/backend changes require `docker compose up -d --build`** — HTML/JS/CSS changes do NOT (volume-mounted).

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
| Domain reorder | Drag-and-drop in Project Tracker (2026-06-14) | Domain rows are draggable in the tracker; sort_order swapped via PATCH. Replaces earlier ▲▼ buttons decision. |
| Daily Log architecture | Option C — ProjectLog only (2026-06-17) | Domain heatmap click-entry removed. Projects tracker is the sole time-entry UI. Domain totals are read-only rollups from ProjectLog. `#hm-wrap` and `#domain-panel` removed from HTML. |
| Project Tracker redesign | Tight spreadsheet grid (2026-06-17) | `#pt-wrap` always visible (no `.open` class needed). Domain bars: thin dark strip with colored accent pip, ▶/▼ arrow, click to collapse/expand via `ptCollapsed` Set. Cells: 52×44px. Dead JS removed: `setTrackerView`, `toggleDomains`, `renderDomainPanel`, `ptOpenDomEdit/Close/Save`, `trackerView`. |
| Bot/scheduler startup | Inside FastAPI lifespan, token-optional | Single process, single container. Missing token → bot DORMANT, everything else runs. Token can be added any time via .env + restart. |
| UI aesthetic | "Workshop" light theme (2026-06-12) — NOT LCARS | Jeff's call: no Star Trek. Warm paper #F7F2EA, ink #221C14, burnt orange #C44A18, deep teal #1E6E62, olive #5C7C2F for todos. System font stack, 14px body, high contrast. Heatmap ramps paper→deep orange; cell text white at ≥4h. CSS vars in `:root` of dashboard.html — restyle there, never in JS logic. |
| App name | "The Board \| Forward Balanced" (2026-06-13) | Jeff's call. Title tag, wordmark, tagline updated. |
| Goals system | `goal_pct` on domains only; underperformers = domains, not projects (2026-06-14) | % of total logged hours target. `weekly_goal` (absolute hrs) kept alongside. `/api/goals` computes week/month/8-week actuals vs target. TODAY shows top-5 underperforming domains. Tracking is at domain level; don't nag about individual projects. |
| ProjectLog rollup | Project hours always roll up to their domain (2026-06-14) | `briefing.py`, `goals.py`, and `project_log.py` all add project_log hours into domain totals. Dormant/behind detection is domain-based; logging at project level counts toward the domain. |
| Project Tracker | Default view = PROJECTS; DOMAINS/PROJECTS toggle on Daily Log tab (2026-06-13/14) | Separate `project_log` table. Project hours roll up to domain totals. PROJECTS is the more useful daily view. |
| Backlog category | BACKLOG = third project category (2026-06-13) | For imported todos pasted from external app. Separate tracker section. |
| Project delete | Soft delete via status='DELETED' (2026-06-13) | Consistent with never destroying data. Hidden from all lists and tracker. |
| Landing page | TODAY tab — agenda-first launchpad (2026-06-12) | Jeff: "great entry dashboard to launch my day… priorities and projects getting behind." Focus card + ordered agenda + 3 cards (priorities / getting behind / social steps). Agenda priority order: overdue social → slipping priorities → due today → scheduled → goals behind → dormant domains. Engine lives in briefing.py `build_brief_data` — ONE source for web TODAY, Telegram brief, and focus. Stale-project nag removed from agenda (2026-06-14). |
| Housekeeping list | Retired from UI/brief/bot (2026-06-12) | Jeff's call. API stays list-generic and house rows remain in DB (soft policy: never destroy history). HOUSE *domain* (heatmap) unaffected — archive via Domain Settings if ever unwanted. |
| Lori's Priorities | Manually ranked list (sort_order), ▲▼ reorder | It's a priority queue, not a todo list — manual order beats due-date sort. #1 = next move. Bot: `/add <text>`, `/check <n>` (lori implied). |
| Social Queue framing | CRM — every contact carries a computed `next_action` | Jeff: "informs me what steps are due to keep on my plan." next_action(phase, due, type) rendered on friend rows, TODAY page, and brief. Logic in routers/social.py. |
| Schema migrations | Inline `_migrate()` in main.py lifespan (PRAGMA check → ALTER) | Zero-ops, idempotent, runs before seed. First use: todos.sort_order. |
| Accent color picker | 64-color palette grid, not free-text hex input (2026-06-14) | Swatch-based picker stays on-palette. `PALETTE_64` const at module level; `.color-picker-grid` CSS class. Hex input removed from project create/edit forms. |
| Diary open behavior | Clicking project opens journal entries first, not settings (2026-06-14) | Settings are one-time; entries are daily. `openDiary()` hides `#diary-mgmt` by default; ⚙ SETTINGS button toggles it. |
| Diary panel position | `position: sticky; top: 72px; max-height: calc(100vh - 90px)` (2026-06-14) | Panel stays in viewport without scrolling. `#diary-panel.open` has overflow-y: auto. |
| Diaries layout | Domain-grouped cards with drag-to-reassign (2026-06-14) | Project cards grouped by domain section (`dom-section`). Dragging a card to a different domain section PATCHes `domain_key`. `domainsList` fetched alongside projects in `loadProjects()`. |
| Domain editor | Popup modal overlay from Diaries domain section headers; inline edit row in tracker (2026-06-14) | Clicking domain header in Diaries opens `#dom-editor-overlay` (fixed, centered modal). Clicking ✎ in tracker domain row opens inline edit row in the table. Both pre-populate from current values. |
| Project-level ∑ column | Shows week hours + all-time total from ProjectLog (2026-06-14) | `all_time_hours` added to `/api/project-log/week` per-project payload and per-domain payload. Tracker ∑ cell shows `Xh` (week) and `Ytot` (all-time). |
| EXERCISE domain | Replaces MTB as standalone domain; 4 projects underneath (2026-06-14) | seed.py: EXERCISE domain + MTB/Biking, Pumping Iron, Swimming, Walking as projects. Existing DBs need manual SQL or UI migration. |

---

## Component / Service Status

| Component | File | Status | Notes |
|---|---|---|---|
| dashboard.html v1 | dashboard.html | **Legacy** — localStorage only | Initial prototype; superseded by v2 |
| FastAPI backend | app/ | **Built + tested** | All routers verified via live server + curl 2026-06-12 |
| Web UI v2 | app/static/dashboard.html | **Built — volume-mounted** | HTML/CSS/JS live on hard-refresh. Last major rewrite 2026-06-14. Full click-through needs browser verification. |
| Telegram bot | app/telegram_bot.py | **Built — dormant** | Starts clean without token; live commands untested (no token yet) |
| Scheduler | app/scheduler.py | **Built + tested** | Fires at BRIEFING_TIME in TZ; briefing text verified via /api/brief |
| xbar plugin | xbar/dashboard.1m.sh | **Built + tested** | Live output + OFFLINE fallback both verified in sandbox |
| Docker | Dockerfile, docker-compose.yml | **Built** | Not yet run on host — needs `docker compose up --build` after 2026-06-14 backend changes |
| briefing.py | app/briefing.py | **Built + updated** | ProjectLog rollup added; stale-project nag removed from agenda |
| goals.py | app/routers/goals.py | **Built + updated** | ProjectLog rollup added; underperformers = domains only |
| project_log.py | app/routers/project_log.py | **Built** | Returns week_hours + all_time_hours per project and per domain |

---

## Build Plan

### Phase 1 — Data skeleton
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 2 — Daily Log API + UI
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 3 — Social Queue API + UI
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 4 — Projects + Todos API + UI
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 5 — Telegram bot + daily briefing
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 6 — xbar menu bar plugin
**Status:** `[x] Built 2026-06-12 — user acceptance pending`

### Phase 7 — Trends + goals
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

### Known Issues / Needs Verification
- Web UI v2 full click-through in a real browser (heatmap clicks, drag & drop, diary panel, domain editor modal, color picker)
- Docker build not yet run on the Mac host after 2026-06-14 backend changes — `docker compose up -d --build` required
- Telegram bot live commands + 7:30 briefing delivery untested — waiting on real token + user ID
- **EXERCISE domain** in existing live DB: MTB is still a standalone domain. Needs SQL migration (see What's Next).

### 2026-06-14 Changes (session 6)
- **ProjectLog rollup**: `briefing.py` now adds `project_log` hours into domain `week` + `recent` totals (dormant/behind detection now counts project-logged hours toward the domain). Same rollup added to `goals.py`.
- **Underperformers = domains only**: `goals.py` top-5 underperformers returns domains only, not projects. TODAY BALANCE GOALS panel shows domain gaps only.
- **Stale-project nag removed**: agenda engine in `briefing.py` no longer emits `kind=project/urgency=stale` items. Domains are the tracking unit; don't nag about individual projects.
- **`/api/project-log/week` shape change**: `total` renamed to `week_hours`; `all_time_hours` added per-project (cumulative across all time). Domain list also includes `all_time_hours` (sum of projects in that domain).
- **Tracker ∑ column**: shows `Xh` (week) and `Ytot` (all-time) from `all_time_hours`.
- **Tracker drag & drop**: domain header rows are `draggable`; drop on another domain header swaps `sort_order` via PATCH. Project rows are `draggable`; drop on a domain header row or another project row reassigns domain (or reorders within domain). `ptDragType` tracks whether we're dragging a domain or a project.
- **64-color accent color picker**: `PALETTE_64` const at module level; `.color-swatch-btn` opens `.color-picker-grid` dropdown; color selected via `.color-swatch` cells. Applied to project create form and diary ⚙ SETTINGS inline edit.
- **Tracker row cleanup**: removed WORK/RESEARCH/BACKLOG category badge column; removed "14d" stale badge. Rows show: color dot, name, ∑ (week + all-time), day cells only.
- **Tracker inline domain edit**: clicking ✎ on domain header row reveals inline edit row (label, wk goal, % goal). Saves via PATCH `/api/domains/{id}`. `ptEditDomId` tracks which domain is open.
- **Tracker domain `all_time_hours`**: domain header rows show all-time hours in ∑ column.
- **Diary entries-first**: `openDiary()` hides `#diary-mgmt` panel by default; shows `#diary-entries` immediately. ⚙ SETTINGS button in diary header toggles management panel.
- **Diary panel sticky**: `#diary-panel.open { position: sticky; top: 72px; max-height: calc(100vh - 90px); overflow-y: auto; }` — no scrolling required to use the diary panel.
- **Diaries domain grouping**: `renderProjects()` rewritten to group project cards into `.dom-section` blocks, one per active domain (ordered by `domainsList`). Each section has a colored `.dom-section-hdr` + `.dom-section-cards` grid. `loadProjects()` fetches both projects and domainsList concurrently.
- **Diaries drag-to-reassign**: project cards are `draggable`; dropping onto a different domain section's card area PATCHes `domain_key` via `/api/projects/{id}`. `diaryDragId` tracks the dragged project.
- **Domain editor popup**: clicking a domain section header in Diaries opens `#dom-editor-overlay` modal (fixed, centered). Pre-populates label/wk_goal/goal_pct from `domainsList`. SAVE, CANCEL, ARCHIVE buttons.
- **EXERCISE domain in seed.py**: MTB domain replaced by EXERCISE; 4 projects seeded under EXERCISE (MTB/Biking, Pumping Iron, Swimming, Walking). Fresh installs get this automatically.

### 2026-06-13 Changes (session 5)
- **PROJECTS default view**: `trackerView` default changed to `'projects'`
- **`renderProjectTracker()` rewrite**: uses `ptData.domains` + `ptData.projects` API shape. Domain header rows colored with `domainColor()`. Category badges: WORK=orange, RESEARCH=teal, BACKLOG=faint. PAUSED projects dimmed. UNASSIGNED section at bottom.
- **`seed.py` EXERCISE domain**: replaced MTB domain with EXERCISE. Added 4 projects under EXERCISE.

### 2026-06-13 Changes (session 4)
- **ProjectLog table**: new `project_log (date, project_id, hours)` table
- **`/api/project-log/week`** and **`POST /api/project-log`**: project-level time tracking
- **Domain rollup**: `/api/log/week` adds project_log hours to domain col_totals
- **Project Tracker UI**: DOMAINS/PROJECTS toggle on Daily Log tab
- **BACKLOG category**, **Project delete** (soft), **Project edit panel**, **4-tab Diaries filter**

### 2026-06-13 Changes (session 3)
- **App renamed**: "The Board | Forward Balanced"
- **`goal_pct` on domains + projects**, **`/api/goals` endpoint**, **TODAY BALANCE GOALS panel**

### 2026-06-13 Changes (session 2)
- **Sort_order collision bug fixed** in `create_friend`
- **`POST /api/friends/spread`**, **`GET /api/friends/stats`**
- **UI**: stats strip, calendar timeline, spread modal

### 2026-06-13 Changes (session 1)
- **Daily Log**: − button on hover; 12-week weekly heatmap view
- **TODAY**: 2×2 grid; Social Queue CRM next_action
- **Schema migrations**: Friend.contact_mode, Friend.sort_order, Friend.advance_days, Project.category

### Current Build Plan Phase
**Active phase:** Verification + Polish — all 7 phases code-complete; user acceptance and live testing pending  
**Remaining:** `docker compose up --build` on host, browser click-through, Telegram token, xbar install

---

## What's Next

0. Jeff, on the Mac: `git add -A && git commit -m "The Board: drag+drop, color picker, sticky diary, domain-grouped diaries, ProjectLog rollup"` (ALL git ops on host — never from sandbox)
1. **Live DB migration for EXERCISE domain** (existing installs only):
   ```sql
   INSERT OR IGNORE INTO domains (key,label,weekly_goal,sort_order,active) VALUES ('EXERCISE','Exercise',0,4,1);
   ```
   Then use the project Edit (⚙ SETTINGS in diary panel) to reassign MTB, Pumping Iron, etc. to EXERCISE, or run SQL directly.
2. Jeff: `docker compose up -d --build` — REBUILD REQUIRED for backend changes (briefing.py, goals.py, project_log.py, seed.py)
3. Hard-refresh browser (Cmd+Shift+R) — HTML is volume-mounted so no rebuild needed for UI
4. Verify in browser: PROJECTS tracker view (drag domains/projects), Diaries domain sections (drag project cards between domains), diary panel sticky, color picker in ⚙ SETTINGS, TODAY goals panel shows domains only
5. Jeff provides real TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USER_ID → restart container → test `/log coding 2` and `/brief`
6. Install xbar plugin: `cp xbar/dashboard.1m.sh ~/.config/xbar/plugins/ && chmod +x ~/.config/xbar/plugins/dashboard.1m.sh`
7. Confirm 7:30am briefing arrives next morning

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
| 2026-06-12 | git commit from sandbox into Dropbox-mounted folder | Commit da48cf4 succeeded, but stale `.git/HEAD.lock` + `.git/index.lock` left behind — sandbox cannot unlink in the mount | Run `rm -f .git/HEAD.lock .git/index.lock` on the Mac before next git operation. Future git work in this repo is best done on the host |
| 2026-06-12 | Second sandbox commit attempt (restyle) after Jeff cleared locks | `git add` succeeded but left a fresh immortal `index.lock`; commit blocked | **RULE: never run git write operations from the sandbox in this repo.** Stage/commit on the Mac only. |
| 2026-06-12 | UPDATE on live data/dashboard.db from sandbox | `sqlite3.OperationalError: disk I/O error` | Mount can't delete SQLite's journal file. Fix: `PRAGMA journal_mode=MEMORY` before writing. Use sparingly — no on-disk rollback journal during the write |
| 2026-06-14 | EXERCISE domain showed "dormant 3+ weeks" on TODAY despite having ProjectLog hours | briefing.py only read DailyLog for week/recent domain totals; ProjectLog hours were ignored | Added ProjectLog rollup loop after DailyLog loop in both `briefing.py` and `goals.py` |
| 2026-06-14 | `apBadge` referenced in `projCard()` return string after being removed from function body | JS parse error / undefined variable | Removed stale `+ apBadge` at end of return string. Always grep for removed variables before declaring a refactor done. |
| 2026-06-14 | `closeProjEditPanel()` called in `saveProjEdit()` after function was renamed | ReferenceError at runtime | Replaced with direct DOM: `document.getElementById('diary-mgmt').classList.remove('open')` |

---

## Session Log

### 2026-06-14 (drag/drop + color picker + diary UX + domain grouping)
**Phase:** Feature evolution — 8 UX improvements + ProjectLog rollup fixes  
**Attempted:** (1) Project hours roll up to domain totals everywhere (goals, briefing, dormant). (2) Don't nag about projects — track domains. (3) Drag & drop domains and projects in tracker. (4) 64-color accent color picker. (5) Remove badge clutter from tracker rows. (6) All-time hours (∑) per project and domain. (7) Diary panel entries-first (settings behind a button). (8) Sticky diary panel (no scrolling). (9) Diaries grouped by domain with drag-to-reassign. (10) Domain editor popup from Diaries section headers.  
**Succeeded:** All 10 items implemented. Backend: `briefing.py` ProjectLog rollup, `goals.py` ProjectLog rollup + domains-only underperformers, `project_log.py` `week_hours`/`all_time_hours` fields. Frontend: `PALETTE_64` color picker, drag state machines (`ptDragType/ptDragId`, `diaryDragId`), `#dom-editor-overlay` modal, sticky diary panel CSS, `renderProjects()` domain-grouped rewrite, `openDiary()` entries-first behavior, tracker ∑ column, inline domain edit row in tracker, category badge column removed.  
**Failed:** Nothing  
**New constraints discovered:** `app/static/` is volume-mounted — HTML changes are live on hard-refresh, no rebuild needed. Python backend changes still require rebuild.  
**Plan changes:** Locked Decisions updated. Domain reorder decision updated from ▲▼ to drag-and-drop.  
**Awaiting user:** `docker compose up -d --build` (backend changed), Cmd+Shift+R in browser (HTML changed), EXERCISE domain SQL migration, git commit on Mac.

### 2026-06-13 (sessions 1–5)
Multiple sessions: social CRM next_action, TODAY tab redesign, app rename, goals system, ProjectLog table, project tracker, EXERCISE seed, sort_order fixes, social stats strip + calendar timeline. See Current State for full change log.

### 2026-06-12 (launchpad rework)
**Phase:** Feature evolution — TODAY landing + priorities + CRM  
**Succeeded:** briefing.py agenda engine, Lori's Priorities reorder, social next_action, TODAY tab, Priorities ranked column, friend rows show next step.  
**Awaiting user:** `docker compose up -d --build`, browser look at TODAY tab, commit on Mac.

### 2026-06-12 (domain rename)
**Phase:** Live data tweak — TECH→CODING, RSS→GAMING  
**Note:** First DB write hit sandbox journal-file limitation (journal_mode=MEMORY workaround documented).

### 2026-06-12 (restyle session)
**Phase:** Post-build polish — LCARS → Workshop light theme  
**Succeeded:** Full re-skin, CSS vars, warmth palette, heatmap ramp, no LCARS references.

### 2026-06-12 (build session)
**Phase:** Phases 1–7 — full system build in one pass  
**Succeeded:** Everything API-tested in sandbox. Dependencies pinned: fastapi 0.136, sqlalchemy 2.0.50, apscheduler 3.11 (v3 API), python-telegram-bot 22.8.

### 2026-06-12 (pre-build)
**Phase:** Requirements and architecture  
**Succeeded:** REQUIREMENTS.md written, CLAUDE.md bootstrapped.

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
