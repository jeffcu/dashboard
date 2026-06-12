"""Summary + Brief endpoints — consumed by xbar plugin, scheduler, and bot."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..briefing import build_brief_data, format_brief_text
from ..database import get_db
from ..models import DailyLog, Domain, Friend, Todo

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=today.weekday())

    domains = (db.query(Domain).filter(Domain.active == True)  # noqa: E712
               .order_by(Domain.sort_order).all())
    by_id = {d.id: d.key for d in domains}
    rows = db.query(DailyLog).filter(DailyLog.date >= start).all()
    week = {d.key: 0 for d in domains}
    for r in rows:
        k = by_id.get(r.domain_id)
        if k:
            week[k] += r.hours

    friends = db.query(Friend).filter(Friend.active == True).all()  # noqa: E712
    overdue = sorted(
        [f for f in friends
         if f.phase == "TO_SCHEDULE" and f.due_date and f.due_date < today],
        key=lambda f: f.due_date)

    todos_today = (db.query(Todo)
                   .filter(Todo.active == True, Todo.done == False,  # noqa: E712
                           Todo.list_id == "lori",
                           Todo.due_date != None, Todo.due_date <= today)  # noqa: E711
                   .all())

    return {
        "date": today.isoformat(),
        "week_total": sum(week.values()),
        "domains": [{"key": d.key, "hours": week[d.key],
                     "goal": d.weekly_goal} for d in domains],
        "overdue_count": len(overdue),
        "overdue": [{"name": f.name, "days": (today - f.due_date).days}
                    for f in overdue],
        "todos_due": [{"text": t.text, "list": t.list_id,
                       "overdue": t.due_date < today} for t in todos_today],
    }


@router.get("/brief")
def get_brief(db: Session = Depends(get_db)):
    data = build_brief_data(db)
    return {"data": data, "text": format_brief_text(data)}


@router.get("/today")
def get_today(db: Session = Depends(get_db)):
    """The morning launchpad — agenda, priorities, what's getting behind."""
    return build_brief_data(db)
