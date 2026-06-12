# Software Requirements Specification
## Personal Systems Dashboard — v2.0
**Author:** Jeff Curie  
**Date:** June 12, 2026  
**Status:** Draft — supersedes v1.0

---

## 1. Purpose

A personal life-balance and social-maintenance system. It helps Jeff stay intentional across a rainbow of shifting projects, research interests, physical health, social relationships, and household responsibilities. The primary interaction loop is: log what you did today, see what needs attention, act from wherever you are.

The system has three clients:
1. **Web UI** — full-featured dashboard, LCARS aesthetic, runs in browser against the local Docker service
2. **Telegram bot** — daily morning briefing pushed to phone; quick-log commands from anywhere
3. **macOS menu bar** — one-click popover showing today's balance and social queue status; launches the web UI

---

## 2. Architecture

| Layer | Technology | Why |
|-------|------------|-----|
| Backend API | Python + FastAPI | Async, lightweight, excellent ecosystem |
| Database | SQLite (via SQLAlchemy) | Zero-ops, single file, survives Docker restarts via volume mount |
| Scheduler | APScheduler (in-process) | Daily briefing cron, no separate container needed |
| Telegram | python-telegram-bot | Best-maintained Python Telegram library |
| Web UI | Single HTML file (vanilla JS) | No build step, served as static file by FastAPI |
| Container | Docker + docker-compose | Portable, restarts on boot, one command to run |
| Menu bar | xbar plugin (shell script) | Free, no native code, calls local API |

### Deployment topology
```
[Docker container: port 8765]
  ├── FastAPI (REST API + static file server)
  ├── SQLite database (volume-mounted at /data/dashboard.db)
  ├── APScheduler (daily 7:30am Telegram briefing)
  └── Telegram bot (polling mode — no public URL needed)

[macOS host]
  └── xbar plugin (refreshes every 5 min, calls localhost:8765/api/summary)

[Telegram]
  └── Private bot — Jeff's personal chat only
```

**Port:** 8765 (avoids macOS reserved ports: 5000=AirPlay, 7000=AirPlay receiver)

---

## 3. Life Domains

The core taxonomy. Domains are stored in the database and can be added, renamed, or archived via the web UI.

| ID | Label | Description |
|----|-------|-------------|
| TECH | Tech | Software development (Trust, Intelligence, D&D) |
| ROBOT | Robot | Robotics experiment and code lab |
| ART | Art | Painting (nocturne oil), sculpture (plasticene) |
| MTB | Mtb | Mountain biking, physical activity |
| SOCIAL | Social | Friend contact, relationship maintenance |
| CIVIC | Civic | Community advocacy (OC Parks, e-bike campaign) |
| FIN | Fin | Financial planning (Roth IRA, scholarship, ADU) |
| RSS | Rss | Research reading, technical study |
| LORI | Lori | Tasks and coordination for Lori |
| HOUSE | House | Household maintenance and logistics |

Domains have an `active` flag. Archived domains are hidden from the heatmap but preserved in historical data.

---

## 4. Module 1 — Daily Log (Heatmap)

### 4.1 Core interactions (unchanged from v1)
- 7-row × N-column grid (days × active domains)
- Left-click cell → +1 hour (max 8)
- Right-click cell → −1 hour (min 0)
- Week navigation: PREV / TODAY / NEXT
- 9-stop amber color scale (#09091c → #FF9922)
- Row totals, column totals, week total

### 4.2 New: Weekly goals
- Each domain has an optional `weekly_goal_hours` integer (0 = no goal)
- Column header shows goal as a small indicator: e.g. `ART ·/5` meaning 5h goal
- Column total color changes: red if week is ending (Fri+) and you're below 60% of goal; green if met
- Goals are set in a Domain Settings panel (gear icon)

### 4.3 New: Cross-week trend panel
- A "TRENDS" toggle below the heatmap expands a secondary view
- Shows the last 8 weeks as a sparkline per domain (total hours per week)
- Highlights domains with zero hours in the last 2 weeks in amber
- Streak counter: consecutive weeks with ≥1 hour logged per domain

### 4.4 New: Domain management
- Domain Settings panel (accessible from heatmap header)
- Add domain: name + optional weekly goal
- Archive domain: hides from heatmap, preserves history
- Edit domain name or goal at any time
- Reorder domains via drag-and-drop (saved to DB)

### 4.5 Data model
```
Table: daily_log
  id          INTEGER PRIMARY KEY
  date        DATE NOT NULL          -- YYYY-MM-DD
  domain_id   INTEGER FK domains.id
  hours       INTEGER (0–8)
  UNIQUE(date, domain_id)

Table: domains
  id            INTEGER PRIMARY KEY
  key           TEXT UNIQUE           -- e.g. 'ART'
  label         TEXT
  weekly_goal   INTEGER DEFAULT 0
  sort_order    INTEGER
  active        BOOLEAN DEFAULT 1
  created_at    DATETIME
```

---

## 5. Module 2 — Project Diaries

### 5.1 Core interactions (unchanged from v1)
- Grid of project cards (4 per row)
- Click card → opens diary panel below
- Append timestamped entries (immutable once saved)
- Entry count shown on card

### 5.2 New: Dynamic project management
- Add project: name, domain association, accent color, note, status
- Project status: `ACTIVE` / `PAUSED` / `DONE`
- Done/Paused projects collapse to a separate "Archive" section below the active grid
- Reactivate archived projects with one click

### 5.3 New: Domain linkage
- Each project card shows its linked domain
- Project diary entries are tagged with the domain, so hours logged in the Daily Log can be annotated with which project they went toward (optional free-text "on project X" field when logging hours)

### 5.4 New: Entry search
- Search box above the diary panel filters entries by text across all projects
- Returns matching entries with project name, date, and excerpt

### 5.5 Data model
```
Table: projects
  id          INTEGER PRIMARY KEY
  key         TEXT UNIQUE
  name        TEXT
  domain_id   INTEGER FK domains.id
  accent_color TEXT
  note        TEXT
  status      TEXT ('ACTIVE','PAUSED','DONE') DEFAULT 'ACTIVE'
  sort_order  INTEGER
  created_at  DATETIME

Table: diary_entries
  id          INTEGER PRIMARY KEY
  project_id  INTEGER FK projects.id
  created_at  DATETIME
  text        TEXT
```

---

## 6. Module 3 — Social Queue

### 6.1 Core phase workflow (unchanged from v1)
```
TO_SCHEDULE → [CALL / CALL+LUNCH] → SCHEDULED → [DONE ✓] → DONE → [RESET] → TO_SCHEDULE
```
Types: PHONE (call only) / LOCAL (call + lunch eligible)

### 6.2 New: Contact history log
- Every phase transition is recorded with a timestamp and optional note
- Each friend row expands to show full contact history: date, action, note
- History is immutable — the record of every connection is permanent

### 6.3 New: Cadence / recurrence
- Each friend has a `cadence_days` field (default: 30)
- When a contact is reset to TO_SCHEDULE, the system sets a `due_date` = last_done + cadence_days
- Friends are sorted in the queue by due_date (overdue first)
- Overdue contacts (past due_date) are visually flagged in red
- "Last contacted" date shown on every friend row

### 6.4 New: Urgency visibility
- At the top of the queue: a count badge showing "X overdue · Y due this week"
- Friends who have never been contacted and are >30 days old get an "aging" indicator

### 6.5 New: Contact notes per interaction
- When advancing from TO_SCHEDULE → SCHEDULED, a modal prompts for a note (e.g., "Lunch at Zinc, Jun 14")
- Note is saved to the contact history entry, not overwriting the static friend note

### 6.6 New: Delete friend
- Trash icon on each row — confirms before deleting
- Deletion is soft (archived, not hard-deleted) so history is preserved

### 6.7 Data model
```
Table: friends
  id            INTEGER PRIMARY KEY
  name          TEXT
  type          TEXT ('PHONE','LOCAL')
  phase         TEXT ('TO_SCHEDULE','SCHEDULED','DONE')
  static_note   TEXT
  cadence_days  INTEGER DEFAULT 30
  due_date      DATE
  last_done_at  DATETIME
  active        BOOLEAN DEFAULT 1
  created_at    DATETIME

Table: contact_history
  id          INTEGER PRIMARY KEY
  friend_id   INTEGER FK friends.id
  action      TEXT ('SCHEDULED','DONE','RESET')
  note        TEXT
  created_at  DATETIME
```

---

## 7. Module 4 — Lori + Housekeeping

### 7.1 Core interactions (unchanged from v1)
- Two independent todo lists (Lori, House)
- Add item, check off, delete
- Side-by-side layout

### 7.2 New: Due dates
- Optional due date field per item (date picker)
- Overdue items shown with red indicator
- Items with no due date appear after dated items, sorted by creation

### 7.3 New: Recurring tasks
- Optional `recur` field: `none` / `weekly` / `monthly` / `custom N days`
- When a recurring item is checked off: it automatically re-creates itself with a new due date
- Recurring indicator shown on item row (↻ icon)

### 7.4 New: Completion history
- Completed items are retained in a collapsed "DONE" section rather than deleted
- Can be cleared in bulk ("Clear completed")
- Individual items can still be hard-deleted

### 7.5 Data model
```
Table: todos
  id            INTEGER PRIMARY KEY
  list_id       TEXT ('lori','house')
  text          TEXT
  done          BOOLEAN DEFAULT 0
  done_at       DATETIME
  due_date      DATE
  recur_type    TEXT ('none','weekly','monthly','custom')
  recur_days    INTEGER
  active        BOOLEAN DEFAULT 1
  created_at    DATETIME
```

---

## 8. Module 5 — Daily Briefing (Telegram)

### 8.1 Morning push message
Sent at **7:30 AM** every day (configurable in .env). Format:

```
📅 DAILY BRIEF — Thursday Jun 12

⏱ THIS WEEK SO FAR
  ART    ████░░ 3h / 5h goal
  TECH   ████████ 5h
  MTB    ░░░░░░ 0h ⚠ 3 weeks no log

📞 SOCIAL QUEUE
  🔴 OVERDUE (2): Greg +45d, Thad +38d
  📅 DUE THIS WEEK: Steve, Michael
  ✅ SCHEDULED: Mitch — Lunch Jun 14

📋 LORI
  • Schedule dentist  ⚠ overdue
  • Pick up dry cleaning  due Sat

🏠 HOUSE
  • ADU school fees  due today
  • Mow lawn  (↻ weekly)

🎯 TODAY'S FOCUS
  [Highest-priority unaddressed item across all modules]
```

### 8.2 Telegram bot commands
Users interact by replying to the bot:

| Command | Effect |
|---------|--------|
| `/log art 3` | Add 3 hours to ART for today |
| `/log mtb 1 yesterday` | Add 1 hour to MTB for yesterday |
| `/done mitch Lunch at Zinc` | Advance Mitch to DONE with note |
| `/schedule greg Call this Thursday` | Advance Greg to SCHEDULED with note |
| `/add lori Schedule dentist` | Add item to Lori list |
| `/add house Mow lawn` | Add item to House list |
| `/check lori 1` | Mark item #1 on Lori list done |
| `/brief` | Request the daily briefing now |
| `/status` | Current week heatmap as text table |

### 8.3 Bot security
- Bot only responds to messages from Jeff's Telegram user ID (set in .env as `TELEGRAM_ALLOWED_USER_ID`)
- All other senders receive no response (silent ignore)
- This is a private bot — no public commands, no /start onboarding

---

## 9. Module 6 — macOS Menu Bar (xbar)

### 9.1 Menu bar display
The xbar plugin polls `GET /api/summary` every 5 minutes.

Menu bar title (compact, always visible):
```
⊕ 12h · 📞 2 overdue
```
(total week hours · overdue contacts count)

### 9.2 Dropdown contents
Clicking the menu bar item reveals:

```
PERSONAL SYSTEMS
─────────────────────
THIS WEEK: 12h logged
  ART ██░░ 3h  MTB ░░░░ 0h ⚠
  TECH ████ 5h  RSS ░░░░ 0h

SOCIAL — 2 OVERDUE
  Greg (+45d)  Thad (+38d)

TODAY'S TODOS
  ⚠ ADU school fees (HOUSE)
  • Schedule dentist (LORI)

─────────────────────
Open Dashboard ↗
Refresh
```

### 9.3 xbar plugin
- Shell script (`dashboard.xbar.sh`) stored in the project repo
- User installs xbar, copies the plugin to `~/.config/xbar/plugins/`
- Plugin calls `curl localhost:8765/api/summary` and formats output per xbar spec
- Falls back gracefully if the Docker service is not running: shows "⊕ OFFLINE"

---

## 10. API Specification

All endpoints under `/api/`. JSON in and out. No authentication (localhost only).

### Daily Log
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/log/week?offset=0` | Full week data + column totals + goals |
| POST | `/api/log` | `{date, domain_key, hours}` — upsert |
| GET | `/api/log/trends?weeks=8` | Per-domain weekly totals for last N weeks |
| GET | `/api/domains` | All domains with goals |
| POST | `/api/domains` | Create domain |
| PATCH | `/api/domains/{id}` | Update name / goal / order / active |

### Projects
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | All projects with entry counts |
| POST | `/api/projects` | Create project |
| PATCH | `/api/projects/{id}` | Update name / status / note / color |
| GET | `/api/diary/{project_id}` | All entries for project |
| POST | `/api/diary/{project_id}` | Append entry |
| GET | `/api/diary/search?q=text` | Full-text search across all entries |

### Social Queue
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/friends` | All friends sorted by due_date |
| POST | `/api/friends` | Create friend |
| PATCH | `/api/friends/{id}` | Update type / cadence / note |
| POST | `/api/friends/{id}/advance` | `{note}` — advance phase |
| POST | `/api/friends/{id}/reset` | Reset to TO_SCHEDULE |
| DELETE | `/api/friends/{id}` | Soft-delete (archive) |
| GET | `/api/friends/{id}/history` | Contact history log |

### Todos
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/todos/{list_id}` | All items for list |
| POST | `/api/todos/{list_id}` | Create item |
| PATCH | `/api/todos/{id}` | Update text / done / due_date / recur |
| DELETE | `/api/todos/{id}` | Soft-delete |

### Summary (for menu bar + briefing)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/summary` | Compact status for menu bar |
| GET | `/api/brief` | Full daily briefing data (used by scheduler + `/brief` command) |

---

## 11. Docker Configuration

### docker-compose.yml structure
```yaml
services:
  dashboard:
    build: .
    ports:
      - "8765:8765"
    volumes:
      - ./data:/data           # SQLite database persists here
      - ./static:/app/static   # Web UI HTML file
    env_file: .env
    restart: unless-stopped
```

### .env variables
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...
BRIEFING_TIME=07:30          # 24h local time
TZ=America/Los_Angeles       # Required for correct cron timing
PORT=8765
```

### Dockerfile
- Base: `python:3.11-slim`
- Installs: fastapi, uvicorn, sqlalchemy, apscheduler, python-telegram-bot
- Entrypoint: `uvicorn app.main:app --host 0.0.0.0 --port 8765`

---

## 12. File Structure

```
dashboard/
├── docker-compose.yml
├── Dockerfile
├── .env                         ← secrets, never committed
├── .env.example                 ← committed, no secrets
├── requirements.txt
├── REQUIREMENTS.md              ← this file
├── CLAUDE.md                    ← project memory
├── data/                        ← volume-mounted, gitignored
│   └── dashboard.db
├── app/
│   ├── main.py                  ← FastAPI app, router registration
│   ├── database.py              ← SQLAlchemy setup, session factory
│   ├── models.py                ← ORM table definitions
│   ├── seed.py                  ← Default domain + friend seeding
│   ├── scheduler.py             ← APScheduler + briefing logic
│   ├── telegram_bot.py          ← Bot command handlers
│   ├── routers/
│   │   ├── log.py
│   │   ├── projects.py
│   │   ├── social.py
│   │   ├── todos.py
│   │   └── summary.py
│   └── static/
│       └── dashboard.html       ← Web UI (single file)
└── xbar/
    └── dashboard.1m.sh          ← xbar plugin (refresh every 1 min)
```

---

## 13. MVP Scope

### In scope (v2.0)
- All four enhanced modules with full database persistence
- REST API backing the web UI
- Telegram daily briefing (push at 7:30am)
- Telegram bot commands: `/log`, `/done`, `/schedule`, `/add`, `/check`, `/brief`, `/status`
- Docker + docker-compose single-command startup
- xbar menu bar plugin
- Weekly goals with progress indicators
- Cross-week trends panel (last 8 weeks)
- Social contact history + cadence/due dates
- Todo due dates + recurring tasks
- Dynamic domain and project management

### Out of scope (deferred)
- Multi-user support — single-user personal tool
- Mobile web optimization — Telegram handles mobile interaction
- Data export UI — use sqlite3 CLI or DB browser directly
- Push notifications beyond Telegram
- OAuth or authentication — localhost only, no public exposure
- Tailscale / remote access — set up separately if desired

---

## 14. Build Plan

### Phase 1 — Data skeleton
**Goal:** FastAPI running in Docker with SQLite, all tables created, seed data loaded, `/api/summary` returning JSON  
**Done when:** `curl localhost:8765/api/summary` returns valid JSON with domains and friend counts  
**Status:** `[ ] Not started`

### Phase 2 — Daily Log API + UI
**Goal:** Web UI heatmap works against the API (not localStorage)  
**Done when:** Can log hours via click, navigate weeks, see totals — all persisted to DB  
**Status:** `[ ] Not started`

### Phase 3 — Social Queue API + UI
**Goal:** Friends list with phase workflow, contact history, due dates  
**Done when:** Can advance Mitch to DONE with a note; history shows the entry; overdue badge shows  
**Status:** `[ ] Not started`

### Phase 4 — Projects + Todos API + UI
**Goal:** Dynamic project management and enhanced todo lists  
**Done when:** Can add a new project, write a diary entry, add a recurring todo with due date  
**Status:** `[ ] Not started`

### Phase 5 — Telegram bot + daily briefing
**Goal:** Bot responds to all commands; 7:30am briefing fires  
**Done when:** `/log art 2` updates DB and bot confirms; briefing arrives at 7:30am  
**Status:** `[ ] Not started`

### Phase 6 — xbar menu bar plugin
**Goal:** Menu bar shows week total and overdue count; opens dashboard on click  
**Done when:** Plugin installed, shows live data, falls back to OFFLINE gracefully  
**Status:** `[ ] Not started`

### Phase 7 — Cross-week trends + goals
**Goal:** Sparklines, streak counters, goal progress indicators  
**Done when:** Trends panel shows 8-week history; column header shows goal progress  
**Status:** `[ ] Not started`

---

## 15. Known Constraints

| Constraint | Note |
|------------|------|
| Localhost only | No public URL, no HTTPS required for v2 — Tailscale optional add-on |
| Telegram polling | Bot uses long-polling (no webhook), so no public URL needed for Telegram either |
| Single user | No auth, no multi-user — this is a personal tool |
| SQLite concurrency | Adequate for one user; do not attempt multi-writer setup |
| xbar refresh | Minimum refresh is 1 second in xbar; set to 1m to avoid API hammering |
| TZ in Docker | Must set TZ env var for APScheduler to fire at correct local time |
| Port 8765 | Chosen to avoid macOS reserved ports (5000, 7000) |

---

*End of REQUIREMENTS.md v2.0*
