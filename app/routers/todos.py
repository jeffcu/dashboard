"""Todos API — due dates, recurrence, completion history."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Todo

router = APIRouter(prefix="/api", tags=["todos"])

VALID_LISTS = ("lori", "house")
VALID_RECUR = ("none", "weekly", "monthly", "custom")


def todo_payload(t: Todo) -> dict:
    today = date.today()
    return {
        "id": t.id, "list_id": t.list_id, "text": t.text,
        "done": t.done,
        "done_at": t.done_at.isoformat() if t.done_at else None,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "overdue": bool(t.due_date and not t.done and t.due_date < today),
        "recur_type": t.recur_type, "recur_days": t.recur_days,
        "created_at": t.created_at.isoformat(),
    }


def sort_todos(items: list[Todo]) -> list[Todo]:
    # open first; dated before undated; soonest due first; then by creation
    return sorted(items, key=lambda t: (
        t.done, t.due_date is None, t.due_date or date.max, t.created_at))


def next_due(t: Todo) -> date | None:
    base = max(date.today(), t.due_date or date.today())
    if t.recur_type == "weekly":
        return base + timedelta(days=7)
    if t.recur_type == "monthly":
        return base + timedelta(days=30)
    if t.recur_type == "custom" and t.recur_days:
        return base + timedelta(days=t.recur_days)
    return None


class TodoCreate(BaseModel):
    text: str
    due_date: date | None = None
    recur_type: str = "none"
    recur_days: int | None = None


class TodoPatch(BaseModel):
    text: str | None = None
    done: bool | None = None
    due_date: date | None = None
    recur_type: str | None = None
    recur_days: int | None = None


@router.get("/todos/{list_id}")
def list_todos(list_id: str, db: Session = Depends(get_db)):
    if list_id not in VALID_LISTS:
        raise HTTPException(404, "list must be lori or house")
    items = (db.query(Todo)
             .filter(Todo.list_id == list_id, Todo.active == True)  # noqa: E712
             .all())
    return [todo_payload(t) for t in sort_todos(items)]


@router.post("/todos/{list_id}")
def create_todo(list_id: str, body: TodoCreate, db: Session = Depends(get_db)):
    if list_id not in VALID_LISTS:
        raise HTTPException(404, "list must be lori or house")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text required")
    if body.recur_type not in VALID_RECUR:
        raise HTTPException(400, f"recur_type must be one of {VALID_RECUR}")
    t = Todo(list_id=list_id, text=text, due_date=body.due_date,
             recur_type=body.recur_type, recur_days=body.recur_days)
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
                           recur_type=t.recur_type, recur_days=t.recur_days)
            db.add(spawned)
    for field in ("text", "due_date", "recur_type", "recur_days"):
        v = getattr(body, field)
        if v is not None:
            setattr(t, field, v)
    db.commit()
    out = todo_payload(t)
    if spawned:
        out["spawned"] = todo_payload(spawned)
    return out


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
        raise HTTPException(404, "list must be lori or house")
    n = (db.query(Todo)
         .filter(Todo.list_id == list_id, Todo.done == True,  # noqa: E712
                 Todo.active == True)  # noqa: E712
         .update({Todo.active: False}))
    db.commit()
    return {"cleared": n}
