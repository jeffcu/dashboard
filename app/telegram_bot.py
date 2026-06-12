"""Telegram bot — private, allowlisted to one user ID, long-polling.

Starts only when TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID are set in .env.
Without them the rest of the system runs normally and the bot stays dormant.

python-telegram-bot v21+ async Application API.
Docs: https://docs.python-telegram-bot.org/  (verified 2026-06-12)
"""
import logging
import os
from datetime import date, datetime, timedelta

from .briefing import build_brief_data, format_brief_text
from .database import SessionLocal
from .models import ContactHistory, DailyLog, Domain, Friend, Todo

logger = logging.getLogger("dashboard.telegram")

_application = None
_allowed_id: int | None = None
_chat_id: int | None = None  # learned from first message; falls back to allowed_id


def _authorized(update) -> bool:
    """Silent ignore for anyone but the allowlisted user."""
    return bool(update.effective_user
                and _allowed_id is not None
                and update.effective_user.id == _allowed_id)


# ── command handlers ─────────────────────────────────────

async def _cmd_log(update, context):
    """/log art 3   or   /log mtb 1 yesterday"""
    if not _authorized(update):
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /log <domain> <hours> [yesterday]")
        return
    key = args[0].upper()
    try:
        hours = int(args[1])
    except ValueError:
        await update.message.reply_text("Hours must be a number.")
        return
    day = date.today()
    if len(args) > 2 and args[2].lower() == "yesterday":
        day -= timedelta(days=1)

    db = SessionLocal()
    try:
        domain = db.query(Domain).filter(Domain.key == key).first()
        if not domain:
            keys = ", ".join(d.key for d in db.query(Domain)
                             .filter(Domain.active == True).all())  # noqa: E712
            await update.message.reply_text(f"Unknown domain {key}. Try: {keys}")
            return
        row = (db.query(DailyLog)
               .filter(DailyLog.date == day, DailyLog.domain_id == domain.id)
               .first())
        if row:
            row.hours = min(8, row.hours + hours)
            total = row.hours
        else:
            total = min(8, max(0, hours))
            db.add(DailyLog(date=day, domain_id=domain.id, hours=total))
        db.commit()
        await update.message.reply_text(
            f"✓ {domain.key} → {total}h on {day.strftime('%a %b %-d')}")
    finally:
        db.close()


def _find_friend(db, name: str) -> Friend | None:
    return (db.query(Friend)
            .filter(Friend.active == True,  # noqa: E712
                    Friend.name.ilike(name))
            .first())


async def _cmd_done(update, context):
    """/done mitch Lunch at Zinc"""
    if not _authorized(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /done <name> [note]")
        return
    name, note = args[0], " ".join(args[1:])
    db = SessionLocal()
    try:
        f = _find_friend(db, name)
        if not f:
            await update.message.reply_text(f"No friend named {name}.")
            return
        f.phase = "DONE"
        f.last_done_at = datetime.now()
        f.due_date = date.today() + timedelta(days=f.cadence_days)
        db.add(ContactHistory(friend_id=f.id, action="DONE", note=note))
        db.commit()
        await update.message.reply_text(
            f"✓ {f.name} → DONE. Next due {f.due_date.strftime('%b %-d')}.")
    finally:
        db.close()


async def _cmd_schedule(update, context):
    """/schedule greg Call this Thursday"""
    if not _authorized(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /schedule <name> [note]")
        return
    name, note = args[0], " ".join(args[1:])
    db = SessionLocal()
    try:
        f = _find_friend(db, name)
        if not f:
            await update.message.reply_text(f"No friend named {name}.")
            return
        f.phase = "SCHEDULED"
        db.add(ContactHistory(friend_id=f.id, action="SCHEDULED", note=note))
        db.commit()
        await update.message.reply_text(
            f"✓ {f.name} → SCHEDULED{(' — ' + note) if note else ''}")
    finally:
        db.close()


async def _cmd_add(update, context):
    """/add lori Schedule dentist"""
    if not _authorized(update):
        return
    args = context.args or []
    if len(args) < 2 or args[0].lower() not in ("lori", "house"):
        await update.message.reply_text("Usage: /add <lori|house> <text>")
        return
    list_id, text = args[0].lower(), " ".join(args[1:])
    db = SessionLocal()
    try:
        db.add(Todo(list_id=list_id, text=text))
        db.commit()
        await update.message.reply_text(f"✓ Added to {list_id.upper()}: {text}")
    finally:
        db.close()


async def _cmd_check(update, context):
    """/check lori 1 — mark item #1 (as numbered in /brief order) done."""
    if not _authorized(update):
        return
    args = context.args or []
    if len(args) < 2 or args[0].lower() not in ("lori", "house"):
        await update.message.reply_text("Usage: /check <lori|house> <number>")
        return
    list_id = args[0].lower()
    try:
        n = int(args[1])
    except ValueError:
        await update.message.reply_text("Number required, e.g. /check lori 1")
        return
    db = SessionLocal()
    try:
        items = (db.query(Todo)
                 .filter(Todo.list_id == list_id, Todo.active == True,  # noqa: E712
                         Todo.done == False).all())  # noqa: E712
        items.sort(key=lambda t: (t.due_date is None, t.due_date or date.max,
                                  t.created_at))
        if not 1 <= n <= len(items):
            await update.message.reply_text(
                f"{list_id.upper()} has {len(items)} open item(s).")
            return
        t = items[n - 1]
        t.done = True
        t.done_at = datetime.now()
        msg = f"✓ Done: {t.text}"
        if t.recur_type != "none":
            from .routers.todos import next_due
            nd = next_due(t)
            db.add(Todo(list_id=t.list_id, text=t.text, due_date=nd,
                        recur_type=t.recur_type, recur_days=t.recur_days))
            msg += f"  (↻ next due {nd.strftime('%b %-d')})"
        db.commit()
        await update.message.reply_text(msg)
    finally:
        db.close()


async def _cmd_brief(update, context):
    if not _authorized(update):
        return
    db = SessionLocal()
    try:
        await update.message.reply_text(format_brief_text(build_brief_data(db)))
    finally:
        db.close()


async def _cmd_status(update, context):
    """Current week as a text table."""
    if not _authorized(update):
        return
    db = SessionLocal()
    try:
        today = date.today()
        start = today - timedelta(days=today.weekday())
        domains = (db.query(Domain).filter(Domain.active == True)  # noqa: E712
                   .order_by(Domain.sort_order).all())
        rows = db.query(DailyLog).filter(DailyLog.date >= start).all()
        grid = {(r.domain_id, r.date): r.hours for r in rows}
        days = [start + timedelta(days=i) for i in range(7)]
        lines = ["WEEK " + start.strftime("%b %-d"),
                 "       " + " ".join(d.strftime("%a")[:2] for d in days)]
        total = 0
        for dom in domains:
            vals = [grid.get((dom.id, d), 0) for d in days]
            total += sum(vals)
            lines.append(f"{dom.key:<7}" +
                         " ".join(str(v) if v else "·" for v in vals) +
                         f"  {sum(vals)}h")
        lines.append(f"TOTAL  {total}h")
        await update.message.reply_text("```\n" + "\n".join(lines) + "\n```",
                                        parse_mode="Markdown")
    finally:
        db.close()


# ── lifecycle ────────────────────────────────────────────

async def start_bot() -> None:
    global _application, _allowed_id, _chat_id
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    user_id = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not token or not user_id:
        logger.info("Telegram bot DORMANT — set TELEGRAM_BOT_TOKEN and "
                    "TELEGRAM_ALLOWED_USER_ID in .env to activate.")
        return
    try:
        _allowed_id = int(user_id)
    except ValueError:
        logger.error("TELEGRAM_ALLOWED_USER_ID must be numeric — bot disabled.")
        return
    _chat_id = _allowed_id  # private bot: chat id == user id

    from telegram.ext import Application, CommandHandler

    _application = Application.builder().token(token).build()
    for cmd, handler in (
        ("log", _cmd_log), ("done", _cmd_done), ("schedule", _cmd_schedule),
        ("add", _cmd_add), ("check", _cmd_check), ("brief", _cmd_brief),
        ("status", _cmd_status),
    ):
        _application.add_handler(CommandHandler(cmd, handler))

    try:
        await _application.initialize()
        await _application.start()
        await _application.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot ACTIVE — polling, allowlisted to %s", _allowed_id)
    except Exception:
        logger.exception("Telegram bot failed to start — continuing without it.")
        _application = None


async def stop_bot() -> None:
    global _application
    if _application:
        try:
            await _application.updater.stop()
            await _application.stop()
            await _application.shutdown()
        except Exception:
            logger.exception("Error stopping Telegram bot")
        _application = None


async def send_daily_briefing() -> None:
    """Called by the scheduler at BRIEFING_TIME."""
    if not _application or _chat_id is None:
        logger.info("Briefing skipped — Telegram bot not active.")
        return
    db = SessionLocal()
    try:
        text = format_brief_text(build_brief_data(db))
    finally:
        db.close()
    try:
        await _application.bot.send_message(chat_id=_chat_id, text=text)
        logger.info("Daily briefing sent.")
    except Exception:
        logger.exception("Failed to send daily briefing")
