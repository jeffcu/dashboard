"""FastAPI app — REST API + static web UI + scheduler + Telegram bot."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .database import Base, SessionLocal, engine
from .routers import log, projects, social, summary, todos
from .seed import seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

STATIC_DIR = Path(__file__).parent / "static"


def _migrate() -> None:
    """Lightweight in-place migrations for existing databases."""
    from sqlalchemy import text
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(todos)"))]
        if cols and "sort_order" not in cols:
            conn.execute(text("ALTER TABLE todos ADD COLUMN sort_order INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE todos SET sort_order = id"))
            conn.commit()
            logger.info("Migrated: todos.sort_order added")


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

app.include_router(log.router)
app.include_router(projects.router)
app.include_router(social.router)
app.include_router(todos.router)
app.include_router(summary.router)


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
