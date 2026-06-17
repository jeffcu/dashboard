"""Social Queue API — contact modes, cadence, CRM history, manual ordering."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ContactHistory, Friend

router = APIRouter(prefix="/api", tags=["social"])

VALID_MODES = ("CALL", "LUNCH", "EITHER")


def next_action(f: Friend, overdue_days: int | None) -> dict:
    """CRM next step based on contact_mode and phase."""
    mode = (getattr(f, "contact_mode", None) or "CALL")

    if f.phase == "TO_SCHEDULE":
        if mode == "LUNCH":
            verb = "Call to schedule lunch"
        elif mode == "EITHER":
            verb = "Call or schedule lunch"
        else:
            verb = "Call"

        if overdue_days:
            return {"text": f"{verb} — {overdue_days}d past plan", "urgency": "overdue"}
        if f.due_date:
            return {"text": f"{verb} by {f.due_date.strftime('%b %-d')}", "urgency": "due"}
        return {"text": f"{verb} — start the cycle", "urgency": "due"}

    if f.phase == "SCHEDULED":
        mode = getattr(f, "contact_mode", "CALL")
        what = "Lunch" if mode == "LUNCH" else "Call"
        note = f" ({f.static_note})" if f.static_note else ""
        return {"text": f"{what} scheduled{note} — mark done when complete", "urgency": "scheduled"}

    nxt = f.due_date.strftime("%b %-d") if f.due_date else "soon"
    return {"text": f"Cycle complete — next up {nxt}", "urgency": "rest"}


def friend_payload(f: Friend) -> dict:
    today = date.today()
    overdue_days = None
    if f.due_date and f.phase == "TO_SCHEDULE" and f.due_date < today:
        overdue_days = (today - f.due_date).days
    aging = (f.last_done_at is None
             and f.phase == "TO_SCHEDULE"
             and (datetime.now() - f.created_at).days > 30)
    return {
        "id": f.id, "name": f.name, "type": f.type, "phase": f.phase,
        "contact_mode": (getattr(f, "contact_mode", None) or "CALL"),
        "sort_order": (getattr(f, "sort_order", None) or 0),
        "advance_days": (getattr(f, "advance_days", None) or 21),
        "static_note": f.static_note, "cadence_days": f.cadence_days,
        "due_date": f.due_date.isoformat() if f.due_date else None,
        "last_done_at": f.last_done_at.isoformat() if f.last_done_at else None,
        "overdue_days": overdue_days, "aging": aging,
        "next_action": next_action(f, overdue_days),
    }


def queue_counts(friends: list[Friend]) -> dict:
    today = date.today()
    week_end = today + timedelta(days=6 - today.weekday())
    overdue = [f for f in friends
               if f.phase == "TO_SCHEDULE" and f.due_date and f.due_date < today]
    due_week = [f for f in friends
                if f.phase == "TO_SCHEDULE" and f.due_date
                and today <= f.due_date <= week_end]
    return {"overdue": len(overdue), "due_this_week": len(due_week)}


class FriendCreate(BaseModel):
    name: str
    type: str = "PHONE"
    contact_mode: str = "CALL"
    cadence_days: int = 30
    advance_days: int = 21
    static_note: str = ""


class FriendPatch(BaseModel):
    name: str | None = None
    type: str | None = None
    contact_mode: str | None = None
    cadence_days: int | None = None
    advance_days: int | None = None
    static_note: str | None = None
    due_date: date | None = None
    sort_order: int | None = None


class AdvanceBody(BaseModel):
    note: str = ""


class NoteBody(BaseModel):
    note: str


class MoveBody(BaseModel):
    direction: str  # "up" or "down"


class SpreadBody(BaseModel):
    window_days: int = 30  # distribute contacts across this many days from today


@router.get("/friends")
def list_friends(db: Session = Depends(get_db)):
    friends = db.query(Friend).filter(Friend.active == True).all()  # noqa: E712
    # sort by manual sort_order (who's on deck)
    friends.sort(key=lambda f: (getattr(f, "sort_order", 0), f.id))
    return {
        "counts": queue_counts(friends),
        "friends": [friend_payload(f) for f in friends],
    }


@router.get("/friends/stats")
def friend_stats(db: Session = Depends(get_db)):
    """Circular queue cycle analytics."""
    today = date.today()
    week_end = today + timedelta(days=6 - today.weekday())
    friends = (db.query(Friend).filter(Friend.active == True)  # noqa: E712
               .order_by(Friend.sort_order, Friend.id).all())
    n = len(friends)
    if n == 0:
        return {"total": 0}

    overdue = [f for f in friends
               if f.phase == "TO_SCHEDULE" and f.due_date and f.due_date < today]
    due_week = [f for f in friends
                if f.phase == "TO_SCHEDULE" and f.due_date
                and today <= f.due_date <= week_end]
    scheduled = [f for f in friends if f.phase == "SCHEDULED"]
    on_schedule = [f for f in friends
                   if not (f.phase == "TO_SCHEDULE" and f.due_date and f.due_date < today)]

    avg_cadence = sum(f.cadence_days for f in friends) / n
    # contacts per month: sum(30/cadence) for each
    monthly = sum(30.0 / f.cadence_days for f in friends)
    # theoretical cycle time: to reach everyone once at combined throughput
    # daily rate = sum(1/cadence) contacts/day; cycle = n / daily_rate
    daily_rate = sum(1.0 / f.cadence_days for f in friends)
    cycle_days = round(n / daily_rate) if daily_rate > 0 else 0
    efficiency_pct = round(len(on_schedule) / n * 100) if n > 0 else 100

    # week buckets for sparkline (next 12 weeks from today)
    week_buckets: dict[int, list[str]] = {}
    for f in friends:
        if f.due_date:
            wk = (f.due_date - today).days // 7
            if -2 <= wk <= 11:
                bucket_key = str(wk)
                week_buckets.setdefault(bucket_key, []).append(f.name)

    return {
        "total": n,
        "overdue": len(overdue),
        "due_this_week": len(due_week),
        "scheduled": len(scheduled),
        "avg_cadence_days": round(avg_cadence),
        "monthly_touchpoints": round(monthly, 1),
        "cycle_days": cycle_days,
        "efficiency_pct": efficiency_pct,
        "week_buckets": week_buckets,
    }


@router.post("/friends/spread")
def spread_friends(body: SpreadBody, db: Session = Depends(get_db)):
    """Distribute TO_SCHEDULE contacts evenly from today across window_days.

    DONE contacts (cycle complete, waiting for next due date) are left untouched.
    Contacts are ordered by their current sort_order (the manual deck order).
    """
    friends = (db.query(Friend).filter(Friend.active == True)  # noqa: E712
               .order_by(Friend.sort_order, Friend.id).all())
    # Only spread contacts that still need action — skip DONE (already handled this cycle)
    to_spread = [f for f in friends if f.phase != "DONE"]
    n = len(to_spread)
    if n == 0:
        return {"spread": 0}
    today = date.today()
    for i, f in enumerate(to_spread):
        days = round(i * body.window_days / max(n - 1, 1))
        f.due_date = today + timedelta(days=days)
        f.phase = "TO_SCHEDULE"
        db.add(ContactHistory(
            friend_id=f.id, action="RESET",
            note=f"Spread from today — window {body.window_days}d (position {i + 1}/{n})"
        ))
    db.commit()
    return {"spread": n, "window_days": body.window_days}


@router.post("/friends")
def create_friend(body: FriendCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    if body.type not in ("PHONE", "LOCAL"):
        raise HTTPException(400, "type must be PHONE or LOCAL")
    if body.contact_mode not in VALID_MODES:
        raise HTTPException(400, "contact_mode must be CALL/LUNCH/EITHER")
    # place at end of queue — use MAX+1 so no collision with existing sort_orders
    max_order_val = db.query(sqlfunc.max(Friend.sort_order)).filter(Friend.active == True).scalar()  # noqa: E712
    max_order = (max_order_val or 0) + 1
    f = Friend(name=name, type=body.type, static_note=body.static_note,
               cadence_days=body.cadence_days, contact_mode=body.contact_mode,
               advance_days=body.advance_days, sort_order=max_order)
    db.add(f)
    db.commit()
    return friend_payload(f)


@router.patch("/friends/{friend_id}")
def patch_friend(friend_id: int, body: FriendPatch, db: Session = Depends(get_db)):
    f = db.get(Friend, friend_id)
    if not f or not f.active:
        raise HTTPException(404, "friend not found")
    if body.type is not None and body.type not in ("PHONE", "LOCAL"):
        raise HTTPException(400, "type must be PHONE or LOCAL")
    if body.contact_mode is not None and body.contact_mode not in VALID_MODES:
        raise HTTPException(400, "contact_mode must be CALL/LUNCH/EITHER")
    for field in ("name", "type", "contact_mode", "cadence_days", "advance_days",
                  "static_note", "due_date", "sort_order"):
        v = getattr(body, field)
        if v is not None:
            setattr(f, field, v)
    db.commit()
    return friend_payload(f)


@router.post("/friends/{friend_id}/advance")
def advance_friend(friend_id: int, body: AdvanceBody, db: Session = Depends(get_db)):
    f = db.get(Friend, friend_id)
    if not f or not f.active:
        raise HTTPException(404, "friend not found")
    mode = (getattr(f, "contact_mode", None) or "CALL")
    advance = (getattr(f, "advance_days", None) or 21)

    if f.phase == "TO_SCHEDULE":
        # CALL/EITHER: single-step — mark DONE right away
        # LUNCH: two-step — call placed (SCHEDULED), await the lunch
        if mode == "LUNCH":
            f.phase = "SCHEDULED"
            action = "SCHEDULED"
        else:
            f.phase = "DONE"
            f.last_done_at = datetime.now()
            f.due_date = date.today() + timedelta(days=f.cadence_days)
            action = "DONE"
    elif f.phase == "SCHEDULED":
        f.phase = "DONE"
        f.last_done_at = datetime.now()
        # for LUNCH: next reminder = cadence_days - advance_days from today
        # (so the call-to-schedule fires advance_days before the target lunch date)
        offset = (f.cadence_days - advance) if mode == "LUNCH" else f.cadence_days
        f.due_date = date.today() + timedelta(days=max(1, offset))
        action = "DONE"
    else:
        raise HTTPException(400, "already DONE — use reset")

    db.add(ContactHistory(friend_id=f.id, action=action, note=body.note.strip()))
    db.commit()
    return friend_payload(f)


@router.post("/friends/{friend_id}/reset")
def reset_friend(friend_id: int, db: Session = Depends(get_db)):
    """Manually restart cycle."""
    f = db.get(Friend, friend_id)
    if not f or not f.active:
        raise HTTPException(404, "friend not found")
    f.phase = "TO_SCHEDULE"
    base = f.last_done_at.date() if f.last_done_at else date.today()
    advance = getattr(f, "advance_days", 21)
    mode = getattr(f, "contact_mode", "CALL")
    f.due_date = base + timedelta(days=(f.cadence_days - advance) if mode == "LUNCH" else f.cadence_days)
    db.add(ContactHistory(friend_id=f.id, action="RESET", note=""))
    db.commit()
    return friend_payload(f)


@router.post("/friends/{friend_id}/requeue")
def requeue_friend(friend_id: int, body: AdvanceBody, db: Session = Depends(get_db)):
    """They reached out — restart cycle from today."""
    f = db.get(Friend, friend_id)
    if not f or not f.active:
        raise HTTPException(404, "friend not found")
    f.phase = "TO_SCHEDULE"
    f.last_done_at = datetime.now()
    advance = getattr(f, "advance_days", 21)
    mode = getattr(f, "contact_mode", "CALL")
    f.due_date = date.today() + timedelta(days=(f.cadence_days - advance) if mode == "LUNCH" else f.cadence_days)
    note = body.note.strip() or "They reached out"
    db.add(ContactHistory(friend_id=f.id, action="REQUEUE", note=note))
    db.commit()
    return friend_payload(f)


@router.post("/friends/{friend_id}/note")
def add_note(friend_id: int, body: NoteBody, db: Session = Depends(get_db)):
    """Add a freeform contact note without changing phase."""
    f = db.get(Friend, friend_id)
    if not f or not f.active:
        raise HTTPException(404, "friend not found")
    note = body.note.strip()
    if not note:
        raise HTTPException(400, "note required")
    db.add(ContactHistory(friend_id=f.id, action="NOTE", note=note))
    db.commit()
    return {"ok": True}


@router.post("/friends/{friend_id}/move")
def move_friend(friend_id: int, body: MoveBody, db: Session = Depends(get_db)):
    """Reorder contact in the deck (▲▼)."""
    friends = (db.query(Friend).filter(Friend.active == True)  # noqa: E712
               .order_by(Friend.sort_order, Friend.id).all())
    idx = next((i for i, f in enumerate(friends) if f.id == friend_id), None)
    if idx is None:
        raise HTTPException(404, "friend not found")
    j = idx - 1 if body.direction == "up" else idx + 1
    if j < 0 or j >= len(friends):
        return friend_payload(friends[idx])
    # swap sort_order values (temp var avoids SQLAlchemy tuple-assign quirks)
    a, b = friends[idx].sort_order, friends[j].sort_order
    friends[idx].sort_order = b
    friends[j].sort_order = a
    db.commit()
    return friend_payload(db.get(Friend, friend_id))


@router.delete("/friends/{friend_id}")
def archive_friend(friend_id: int, db: Session = Depends(get_db)):
    """Soft-delete only — contact history is permanent."""
    f = db.get(Friend, friend_id)
    if not f or not f.active:
        raise HTTPException(404, "friend not found")
    f.active = False
    db.commit()
    return {"archived": f.id}


@router.get("/friends/{friend_id}/history")
def friend_history(friend_id: int, db: Session = Depends(get_db)):
    f = db.get(Friend, friend_id)
    if not f:
        raise HTTPException(404, "friend not found")
    rows = (db.query(ContactHistory)
            .filter(ContactHistory.friend_id == friend_id)
            .order_by(ContactHistory.created_at.desc()).all())
    return [{"id": h.id, "action": h.action, "note": h.note,
             "created_at": h.created_at.isoformat()} for h in rows]
