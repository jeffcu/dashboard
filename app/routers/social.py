"""Social Queue API — phase workflow, contact history, cadence."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ContactHistory, Friend

router = APIRouter(prefix="/api", tags=["social"])


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
        "static_note": f.static_note, "cadence_days": f.cadence_days,
        "due_date": f.due_date.isoformat() if f.due_date else None,
        "last_done_at": f.last_done_at.isoformat() if f.last_done_at else None,
        "overdue_days": overdue_days, "aging": aging,
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
    static_note: str = ""
    cadence_days: int = 30


class FriendPatch(BaseModel):
    name: str | None = None
    type: str | None = None
    static_note: str | None = None
    cadence_days: int | None = None
    due_date: date | None = None


class AdvanceBody(BaseModel):
    note: str = ""


@router.get("/friends")
def list_friends(db: Session = Depends(get_db)):
    friends = db.query(Friend).filter(Friend.active == True).all()  # noqa: E712
    # overdue first (most overdue at top), then due soonest, then no due date
    friends.sort(key=lambda f: (f.due_date is None,
                                f.due_date or date.max,
                                f.name.lower()))
    return {
        "counts": queue_counts(friends),
        "friends": [friend_payload(f) for f in friends],
    }


@router.post("/friends")
def create_friend(body: FriendCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    if body.type not in ("PHONE", "LOCAL"):
        raise HTTPException(400, "type must be PHONE or LOCAL")
    f = Friend(name=name, type=body.type, static_note=body.static_note,
               cadence_days=body.cadence_days)
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
    for field in ("name", "type", "static_note", "cadence_days", "due_date"):
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
    if f.phase == "TO_SCHEDULE":
        f.phase = "SCHEDULED"
        action = "SCHEDULED"
    elif f.phase == "SCHEDULED":
        f.phase = "DONE"
        f.last_done_at = datetime.now()
        f.due_date = date.today() + timedelta(days=f.cadence_days)
        action = "DONE"
    else:
        raise HTTPException(400, "already DONE — use reset")
    db.add(ContactHistory(friend_id=f.id, action=action, note=body.note.strip()))
    db.commit()
    return friend_payload(f)


@router.post("/friends/{friend_id}/reset")
def reset_friend(friend_id: int, db: Session = Depends(get_db)):
    f = db.get(Friend, friend_id)
    if not f or not f.active:
        raise HTTPException(404, "friend not found")
    f.phase = "TO_SCHEDULE"
    base = f.last_done_at.date() if f.last_done_at else date.today()
    f.due_date = base + timedelta(days=f.cadence_days)
    db.add(ContactHistory(friend_id=f.id, action="RESET", note=""))
    db.commit()
    return friend_payload(f)


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
