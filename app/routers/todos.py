"""Todos API — VIP Priorities: manually orderable, due dates, recurrence.

The 'house' list is retired from the UI/briefing but the API stays
list-generic so historical house rows remain readable.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Todo

router = APIRouter(prefix="/api", tags=["todos"])

VALID_LISTS = ("vip", "todo", "house")
VALID_RECUR = ("none", "weekly", "monthly", "custom")


def todo_payload(t: Todo) -> dict:
    today = date.today()
    return {
        "id": t.id, "list_id": t.list_id, "text": t.text,
        "note": t.note or "",
        "done": t.done,
        "done_at": t.done_at.isoformat() if t.done_at else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "overdue": bool(t.due_date and not t.done and t.due_date < today),
        "due_today": bool(t.due_date and not t.done and t.due_date == today),
        "recur_type": t.recur_type, "recur_days": t.recur_days,
        "sort_order": t.sort_order,
        "created_at": t.created_at.isoformat(),
    }


def sort_todos(items: list[Todo]) -> list[Todo]:
    # open items in MANUAL order (it's a priority list); done items last, newest first
    return sorted(items, key=lambda t: (
        t.done,
        t.sort_order if not t.done else 0,
        -(t.done_at.timestamp() if t.done_at else 0),
    ))


def next_due(t: Todo) -> date | None:
    base = max(date.today(), t.due_date or date.today())
    if t.recur_type == "weekly":
        return base + timedelta(days=7)
    if t.recur_type == "monthly":
        return base + timedelta(days=30)
    if t.recur_type == "custom" and t.recur_days:
        return base + timedelta(days=t.recur_days)
    return None


def _next_sort_order(db: Session, list_id: str) -> int:
    mx = (db.query(func.max(Todo.sort_order))
          .filter(Todo.list_id == list_id, Todo.active == True)  # noqa: E712
          .scalar())
    return (mx or 0) + 1


class TodoCreate(BaseModel):
    text: str
    due_date: date | None = None
    recur_type: str = "none"
    recur_days: int | None = None


class TodoPatch(BaseModel):
    text: str | None = None
    note: str | None = None
    done: bool | None = None
    due_date: date | None = None
    recur_type: str | None = None
    recur_days: int | None = None


class MoveBody(BaseModel):
    direction: str  # 'up' | 'down'


@router.get("/todos/{list_id}")
def list_todos(list_id: str, db: Session = Depends(get_db)):
    if list_id not in VALID_LISTS:
        raise HTTPException(404, "unknown list")
    items = (db.query(Todo)
             .filter(Todo.list_id == list_id, Todo.active == True)  # noqa: E712
             .all())
    return [todo_payload(t) for t in sort_todos(items)]


@router.post("/todos/{list_id}")
def create_todo(list_id: str, body: TodoCreate, db: Session = Depends(get_db)):
    if list_id not in VALID_LISTS:
        raise HTTPException(404, "unknown list")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text required")
    if body.recur_type not in VALID_RECUR:
        raise HTTPException(400, f"recur_type must be one of {VALID_RECUR}")
    t = Todo(list_id=list_id, text=text, due_date=body.due_date,
             recur_type=body.recur_type, recur_days=body.recur_days,
             sort_order=_next_sort_order(db, list_id))
    db.add(t)
    db.commit()
    return todo_payload(t)


@router.patch("/todos/{todo_id}")
def patch_todo(todo_id: int, body: TodoPatch, db: Session = Depends(get_db)):
    t = db.get(Todo, todo_id)
    if not t or not t.active:
        raise HTTPException(404, "todo not found")
    if body.recur_type is not None and body.recur_type not in VALID_RECUR:
        raise HTTPException(400, f"recur_type must be one of {VALID_RECUR}")
    spawned = None
    if body.done is not None and body.done != t.done:
        t.done = body.done
        t.done_at = datetime.now() if body.done else None
        # recurring item checked off → spawn the next occurrence
        if body.done and t.recur_type != "none":
            nd = next_due(t)
            spawned = Todo(list_id=t.list_id, text=t.text, due_date=nd,
                           recur_type=t.recur_type, recur_days=t.recur_days,
                           sort_order=_next_sort_order(db, t.list_id))
            db.add(spawned)
    for field in ("text", "note", "due_date", "recur_type", "recur_days"):
        v = getattr(body, field)
        if v is not None:
            setattr(t, field, v)
    db.commit()
    out = todo_payload(t)
    if spawned:
        out["spawned"] = todo_payload(spawned)
    return out


@router.post("/todos/{todo_id}/move")
def move_todo(todo_id: int, body: MoveBody, db: Session = Depends(get_db)):
    """Swap with the neighbor above/below among open items in the same list."""
    t = db.get(Todo, todo_id)
    if not t or not t.active:
        raise HTTPException(404, "todo not found")
    if body.direction not in ("up", "down"):
        raise HTTPException(400, "direction must be up or down")
    open_items = sorted(
        db.query(Todo).filter(Todo.list_id == t.list_id,
                              Todo.active == True,  # noqa: E712
                              Todo.done == False).all(),  # noqa: E712
        key=lambda x: x.sort_order)
    idx = next((i for i, x in enumerate(open_items) if x.id == t.id), None)
    if idx is None:
        raise HTTPException(400, "item is not open")
    j = idx - 1 if body.direction == "up" else idx + 1
    if j < 0 or j >= len(open_items):
        return {"moved": False}
    open_items[idx].sort_order, open_items[j].sort_order = \
        open_items[j].sort_order, open_items[idx].sort_order
    db.commit()
    return {"moved": True}


@router.delete("/todos/{todo_id}")
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    """Soft-delete (active=0)."""
    t = db.get(Todo, todo_id)
    if not t or not t.active:
        raise HTTPException(404, "todo not found")
    t.active = False
    db.commit()
    return {"deleted": t.id}


@router.post("/todos/{list_id}/clear_completed")
def clear_completed(list_id: str, db: Session = Depends(get_db)):
    if list_id not in VALID_LISTS:
        raise HTTPException(404, "unknown list")
    n = (db.query(Todo)
         .filter(Todo.list_id == list_id, Todo.done == True,  # noqa: E712
                 Todo.active == True)  # noqa: E712
         .update({Todo.active: False}))
    db.commit()
    return {"cleared": n}
