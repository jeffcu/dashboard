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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # tables + seed
    Base.metadata.create_all(bind=engine)
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
