# The Board — Goal Manager

> A personal life-balance dashboard. One `docker compose up` and you have a web UI, a Telegram bot, and a macOS menu bar widget — all talking to the same SQLite database.

---

## What It Does

**The Board** tracks how you invest your time across the areas of life that matter to you — creative work, physical health, civic involvement, finances, relationships — and surfaces a prioritized daily agenda so you always know what deserves attention next.

Three clients, one data source:

| Client | Best for |
|---|---|
| **Web dashboard** (`:8765`) | Morning planning, detailed logging, project journals |
| **Telegram bot** | Quick logging and briefing from your phone |
| **macOS menu bar** (xbar) | Glanceable hourly status without opening a browser |

---

## Features

### TODAY — Morning Launchpad
- **Focus card** — single most important thing right now
- **Ordered agenda** — overdue social commitments → slipping priorities → goals behind → dormant domains
- **VIP Priorities snapshot** — your manually-ranked priority queue
- **Balance goals panel** — domains underperforming against weekly targets

### Daily Log
- **Click-to-increment heatmap** — domain × day grid, click a cell to add an hour
- **Week navigation** — step back through any week
- **12-week trend heatmap** — spot drift across quarters at a glance
- **Project tracker** — log time at the project level; hours roll up to domain totals automatically
- **Domain settings** — set weekly hour goals and percentage-of-week targets per domain

### Diaries
- **Project cards grouped by domain** — drag to reassign between domains
- **Sticky journal panel** — entries-first, settings tucked behind a button
- **Full-text search** across all project journals
- **64-color accent picker** — keeps project cards on-palette

### Keep in Touch
- Every contact has a **phase**: `TO_SCHEDULE → SCHEDULED → DONE`
- **next_action** computed per contact based on phase, due date, and contact mode (call / lunch / either)
- Overdue contacts surface in red; due-this-week in amber
- Contact history preserved on every interaction
- Stats strip: overdue count, scheduled, average cadence

### VIP Priorities
- Manually-ranked priority queue (drag or ▲▼)
- Due dates, overdue flags, weekly recurrence
- Soft-delete preserves history

### Telegram Bot
```
/brief          — full morning briefing
/log coding 2  — add 2 hours to the Coding domain
/add Pay quarterly taxes  — add to VIP Priorities
/check 1        — mark priority #1 done
/queue          — social steps due
```

### Daily Briefing (7:30am push)
```
📅 DAILY BRIEF — Tuesday Jun 17

🎯 TODAY'S FOCUS
  Call to schedule lunch — Mitch +3d past plan

📌 AGENDA
  🔴 Call to schedule lunch — Mitch +3d past plan
  ⏱ CODING: 3h of 10h weekly goal

⏱ THIS WEEK SO FAR
  CODING  ███░░░░░░░  3h / 10h goal
  ART     ██████████  8h / 6h goal  ✓

📞 SOCIAL — STEPS DUE
  🔴 Mitch: Call to schedule lunch — 3d past plan

📋 VIP PRIORITIES
  1. Pay quarterly taxes  due Jun 30
  2. Review insurance renewal
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | Python · FastAPI (async) |
| Database | SQLite · SQLAlchemy 2.0 |
| Scheduler | APScheduler 3.x (in-process cron) |
| Telegram | python-telegram-bot 22.x (long-polling — no public URL needed) |
| Web UI | Single HTML file · Vanilla JS · no build step |
| Container | Docker + docker-compose |
| Menu bar | xbar (macOS) |

---

## Architecture

```
┌─────────────────────────────────────────┐
│  Docker container  :8765                │
│                                         │
│  FastAPI ─── REST API + static files    │
│  SQLite  ─── /data/dashboard.db         │
│  APScheduler ── 7:30am briefing         │
│  Telegram bot ── long-polling           │
└──────────────┬──────────────────────────┘
               │ localhost
       ┌───────┴──────────┐
       │                  │
  Browser            xbar plugin
  :8765              polls /api/summary
                     every 60s
```

The Telegram bot connects outbound to Telegram's servers — no webhook, no public URL, no SSL certificate required.

---

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A Telegram bot token ([create one with @BotFather](https://core.telegram.org/bots#botfather)) — **optional**, the app runs without it
- [xbar](https://xbarapp.com/) — **optional**, for the macOS menu bar widget

### 1. Clone and configure

```bash
git clone https://github.com/jeffcu/dashboard.git
cd dashboard
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=        # leave blank to run without Telegram
TELEGRAM_ALLOWED_USER_ID=  # your numeric Telegram user ID
BRIEFING_TIME=07:30
TZ=America/Los_Angeles
PORT=8765
```

Find your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot).

### 2. Start

```bash
docker compose up -d
```

Open **http://localhost:8765** in your browser.

To rebuild after changing Python files:
```bash
docker compose up -d --build
```

HTML / CSS / JS changes in `app/static/` are **live on hard-refresh** (Cmd+Shift+R) — no rebuild needed.

### 3. Menu bar widget (optional)

```bash
cp xbar/dashboard.1m.sh ~/.config/xbar/plugins/
chmod +x ~/.config/xbar/plugins/dashboard.1m.sh
```

Refresh xbar. The plugin polls `/api/summary` every 60 seconds and shows week hours + social queue status.

---

## Configuration

### Domains

Domains are the top-level categories you track time against (e.g. Coding, Art, Exercise, Finance). On first run, a default set is seeded. Customize them in **Daily Log → Domain Settings** or via the domain editor in the Diaries tab.

Each domain can have:
- **Weekly hour goal** — absolute hours per week
- **Goal %** — percentage of total logged hours

### Projects

Projects live inside domains and have their own journal (diary). Create them in the **Diaries** tab. Time logged at the project level rolls up to the parent domain automatically.

### Social Contacts

Add contacts in the **Social** tab. Set a contact mode (Call / Lunch / Either) and a cadence in days. The system computes what action is due and surfaces overdue contacts in the daily agenda.

---

## Customizing for Your Life

This is a personal tool — the default seed data reflects one person's domains and projects. Before first run (or after clearing the database), edit `app/seed.py` to replace the defaults with your own:

```python
DEFAULT_DOMAINS = [
    ("CODING", "Coding"), ("ART", "Art"), ("EXERCISE", "Exercise"),
    ("SOCIAL", "Social"), ("CIVIC", "Civic"), ("FIN", "Finance"),
    # add your own...
]
```

Delete `data/dashboard.db` to start fresh with your seed data.

---

## API Reference

The full REST API is available at `http://localhost:8765/docs` (FastAPI's built-in Swagger UI) when the container is running.

Key endpoints:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/today` | Agenda engine data (TODAY tab) |
| `GET` | `/api/brief` | Full briefing text |
| `GET` | `/api/summary` | xbar summary payload |
| `GET/POST/PATCH` | `/api/log` | Daily time log |
| `GET/POST/PATCH` | `/api/project-log` | Project-level time log |
| `GET/POST` | `/api/domains` | Domain list and settings |
| `GET/POST/PATCH` | `/api/projects` | Projects (diaries) |
| `GET/POST` | `/api/diary/{project_id}` | Journal entries |
| `GET/POST/PATCH` | `/api/friends` | Social contacts |
| `GET` | `/api/goals` | Goal underperformer engine |
| `GET/POST/PATCH` | `/api/todos/{list_id}` | VIP Priorities (`vip`) |

---

## File Structure

```
dashboard/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── app/
│   ├── main.py             # FastAPI app, router registration, migrations
│   ├── database.py         # SQLAlchemy setup
│   ├── models.py           # ORM table definitions
│   ├── seed.py             # Default domain + contact seeding
│   ├── briefing.py         # Agenda engine (single source for web, Telegram, scheduler)
│   ├── scheduler.py        # APScheduler — fires daily briefing
│   ├── telegram_bot.py     # Bot command handlers
│   ├── routers/
│   │   ├── log.py          # Daily time log
│   │   ├── project_log.py  # Project-level time tracking
│   │   ├── projects.py     # Projects + diary entries
│   │   ├── goals.py        # Goal underperformer engine
│   │   ├── social.py       # Keep in Touch + contact history
│   │   ├── todos.py        # VIP Priorities
│   │   └── summary.py      # Summary + brief endpoints
│   └── static/
│       └── dashboard.html  # Entire web UI (volume-mounted, live on refresh)
└── xbar/
    └── dashboard.1m.sh     # macOS menu bar plugin
```

---

## Data & Privacy

- All data is stored locally in `data/dashboard.db` (SQLite)
- The database directory is volume-mounted — data survives container restarts and rebuilds
- Nothing is sent to external services except: the Telegram API (if a bot token is configured) to deliver the daily briefing
- The `data/` directory and `.env` file are gitignored — your personal data never touches version control

---

## Contributing

Pull requests welcome. A few things to know before diving in:

- **No build step for the UI.** `app/static/dashboard.html` is a single file served directly. Changes are live on hard-refresh.
- **Python changes require a rebuild.** `docker compose up -d --build` after any `.py` change.
- **Schema changes** go in the `_migrate()` function in `app/main.py` — idempotent `ALTER TABLE` or `CREATE TABLE IF NOT EXISTS` statements that run on every startup.
- **The agenda engine** (`app/briefing.py` → `build_brief_data()`) is the single source of truth for the TODAY tab, the Telegram `/brief` command, and the scheduler push. Changes there affect all three.
- **Domain hours = DailyLog + ProjectLog.** The goals and briefing engines both roll up project-level hours into domain totals. Keep this invariant when touching either table.

### Running locally without Docker

```bash
pip install -r requirements.txt
DB_PATH=./data/dashboard.db uvicorn app.main:app --reload --port 8765
```

---

## License

MIT — do whatever you like with it. If you build something interesting on top of it, a mention would be appreciated.
