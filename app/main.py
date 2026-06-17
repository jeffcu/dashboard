"""FastAPI app — REST API + static web UI + scheduler + Telegram bot."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .database import Base, SessionLocal, engine
from .routers import goals, log, project_log, projects, social, summary, todos
from .seed import seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

STATIC_DIR = Path(__file__).parent / "static"


def _migrate() -> None:
    """Lightweight in-place migrations for existing databases."""
    from sqlalchemy import text
    with engine.connect() as conn:
        # todos
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(todos)"))]
        if cols and "sort_order" not in cols:
            conn.execute(text("ALTER TABLE todos ADD COLUMN sort_order INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE todos SET sort_order = id"))
            conn.commit()
            logger.info("Migrated: todos.sort_order added")

        # friends — new social CRM fields
        fcols = [r[1] for r in conn.execute(text("PRAGMA table_info(friends)"))]
        if fcols:
            changed = False
            if "contact_mode" not in fcols:
                conn.execute(text("ALTER TABLE friends ADD COLUMN contact_mode VARCHAR DEFAULT 'CALL'"))
                changed = True
            if "sort_order" not in fcols:
                conn.execute(text("ALTER TABLE friends ADD COLUMN sort_order INTEGER DEFAULT 0"))
                conn.execute(text("UPDATE friends SET sort_order = id WHERE sort_order IS NULL OR sort_order = 0"))
                changed = True
            if "advance_days" not in fcols:
                conn.execute(text("ALTER TABLE friends ADD COLUMN advance_days INTEGER DEFAULT 21"))
                changed = True
            if changed:
                # backfill NULLs for existing rows (SQLite DEFAULT is not always written)
                conn.execute(text("UPDATE friends SET contact_mode = 'CALL' WHERE contact_mode IS NULL"))
                conn.execute(text("UPDATE friends SET advance_days = 21 WHERE advance_days IS NULL"))
                conn.commit()
                logger.info("Migrated: friends contact_mode/sort_order/advance_days added")

        # projects — category and check_in_days fields
        pcols = [r[1] for r in conn.execute(text("PRAGMA table_info(projects)"))]
        if pcols:
            pchanged = False
            if "category" not in pcols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN category VARCHAR DEFAULT 'WORK'"))
                pchanged = True
            if "check_in_days" not in pcols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN check_in_days INTEGER DEFAULT 14"))
                pchanged = True
            if "goal_pct" not in pcols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN goal_pct INTEGER DEFAULT 0"))
                pchanged = True
            if pchanged:
                conn.execute(text("UPDATE projects SET category = 'WORK' WHERE category IS NULL"))
                conn.execute(text("UPDATE projects SET check_in_days = 14 WHERE check_in_days IS NULL"))
                conn.execute(text("UPDATE projects SET goal_pct = 0 WHERE goal_pct IS NULL"))
                conn.commit()
                logger.info("Migrated: projects.category/check_in_days/goal_pct added")

        # domains — goal_pct field
        dcols = [r[1] for r in conn.execute(text("PRAGMA table_info(domains)"))]
        if dcols and "goal_pct" not in dcols:
            conn.execute(text("ALTER TABLE domains ADD COLUMN goal_pct INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE domains SET goal_pct = 0 WHERE goal_pct IS NULL"))
            conn.commit()
            logger.info("Migrated: domains.goal_pct added")

        # project_log table (project-level time tracking)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS project_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                project_id INTEGER NOT NULL REFERENCES projects(id),
                hours INTEGER DEFAULT 0,
                UNIQUE(date, project_id)
            )
        """))
        conn.commit()

        # projects — BACKLOG category support (no schema change needed; it's a string value)
        # projects — ensure DELETED status rows exist (no schema change needed)

        # rename 'lori' list_id → 'vip' and LORI domain key → VIP
        conn.execute(text("UPDATE todos SET list_id='vip' WHERE list_id='lori'"))
        conn.execute(text("UPDATE domains SET key='VIP', label='VIP' WHERE key='LORI'"))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # tables + migrations + seed
    Base.metadata.create_all(bind=engine)
    _migrate()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()

    # scheduler (daily briefing)
    from .scheduler import start_scheduler, stop_scheduler
    start_scheduler()

    # telegram bot — starts only if token configured
    from .telegram_bot import start_bot, stop_bot
    await start_bot()

    yield

    await stop_bot()
    stop_scheduler()


app = FastAPI(title="Personal Systems Dashboard", lifespan=lifespan)

# Only allow requests originating from localhost — blocks cross-site requests
# from other browser tabs trying to hit this local API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    ],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(log.router)
app.include_router(projects.router)
app.include_router(social.router)
app.include_router(todos.router)
app.include_router(summary.router)
app.include_router(goals.router)
app.include_router(project_log.router)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/api/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0",
                port=int(os.environ.get("PORT", "8765")))
