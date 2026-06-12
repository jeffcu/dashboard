"""Daily briefing builder — shared by /api/brief, the scheduler, and the bot."""
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .models import DailyLog, Domain, Friend, Todo


def _week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def build_brief_data(db: Session) -> dict:
    today = date.today()
    start = _week_start()
    week_end = today + timedelta(days=6 - today.weekday())

    domains = (db.query(Domain).filter(Domain.active == True)  # noqa: E712
               .order_by(Domain.sort_order).all())
    by_id = {d.id: d.key for d in domains}

    # this week's hours per domain
    rows = db.query(DailyLog).filter(DailyLog.date >= start).all()
    week = {d.key: 0 for d in domains}
    for r in rows:
        k = by_id.get(r.domain_id)
        if k:
            week[k] += r.hours

    # dormancy: zero hours in last 2 full weeks + this week
    two_weeks_ago = start - timedelta(weeks=2)
    old_rows = (db.query(DailyLog)
                .filter(DailyLog.date >= two_weeks_ago, DailyLog.date < start).all())
    recent = {d.key: 0 for d in domains}
    for r in old_rows:
        k = by_id.get(r.domain_id)
        if k:
            recent[k] += r.hours

    domain_lines = [{
        "key": d.key, "hours": week[d.key], "goal": d.weekly_goal,
        "dormant": week[d.key] == 0 and recent[d.key] == 0,
    } for d in domains]

    friends = db.query(Friend).filter(Friend.active == True).all()  # noqa: E712
    overdue = sorted(
        [f for f in friends
         if f.phase == "TO_SCHEDULE" and f.due_date and f.due_date < today],
        key=lambda f: f.due_date)
    due_week = [f for f in friends
                if f.phase == "TO_SCHEDULE" and f.due_date
                and today <= f.due_date <= week_end]
    scheduled = [f for f in friends if f.phase == "SCHEDULED"]

    def todo_list(list_id: str) -> list[dict]:
        items = (db.query(Todo)
                 .filter(Todo.list_id == list_id, Todo.active == True,  # noqa: E712
                         Todo.done == False).all())  # noqa: E712
        items.sort(key=lambda t: (t.due_date is None, t.due_date or date.max))
        return [{
            "text": t.text,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "overdue": bool(t.due_date and t.due_date < today),
            "due_today": t.due_date == today,
            "recur": t.recur_type if t.recur_type != "none" else None,
        } for t in items]

    lori, house = todo_list("lori"), todo_list("house")

    # today's focus: most overdue friend > overdue todo > most-behind goal
    focus = None
    if overdue:
        f = overdue[0]
        focus = f"Reach out to {f.name} — {(today - f.due_date).days}d overdue"
    else:
        od = [t for t in lori + house if t["overdue"]]
        if od:
            focus = f"Clear overdue todo: {od[0]['text']}"
        else:
            behind = [dl for dl in domain_lines
                      if dl["goal"] and dl["hours"] < dl["goal"]]
            if behind:
                b = max(behind, key=lambda x: x["goal"] - x["hours"])
                focus = f"Log time on {b['key']} — {b['hours']}h of {b['goal']}h goal"
    if not focus:
        focus = "All systems nominal — pick something fun"

    return {
        "date": today.isoformat(),
        "domains": domain_lines,
        "week_total": sum(week.values()),
        "social": {
            "overdue": [{"name": f.name, "days": (today - f.due_date).days}
                        for f in overdue],
            "due_this_week": [f.name for f in due_week],
            "scheduled": [{"name": f.name, "note": f.static_note}
                          for f in scheduled],
        },
        "lori": lori,
        "house": house,
        "focus": focus,
    }


def _bar(hours: int, goal: int) -> str:
    width = max(goal, hours, 6)
    filled = min(hours, width)
    return "█" * filled + "░" * (width - filled)


def format_brief_text(data: dict) -> str:
    d = datetime.fromisoformat(data["date"])
    lines = [f"📅 DAILY BRIEF — {d.strftime('%A %b %-d')}", ""]

    lines.append("⏱ THIS WEEK SO FAR")
    for dom in data["domains"]:
        goal = f" / {dom['goal']}h goal" if dom["goal"] else ""
        warn = "  ⚠ no log 3+ weeks" if dom["dormant"] else ""
        lines.append(f"  {dom['key']:<7}{_bar(dom['hours'], dom['goal'])} "
                     f"{dom['hours']}h{goal}{warn}")
    lines.append("")

    s = data["social"]
    lines.append("📞 SOCIAL QUEUE")
    if s["overdue"]:
        names = ", ".join(f"{o['name']} +{o['days']}d" for o in s["overdue"])
        lines.append(f"  🔴 OVERDUE ({len(s['overdue'])}): {names}")
    if s["due_this_week"]:
        lines.append(f"  📅 DUE THIS WEEK: {', '.join(s['due_this_week'])}")
    for sc in s["scheduled"]:
        note = f" — {sc['note']}" if sc["note"] else ""
        lines.append(f"  ✅ SCHEDULED: {sc['name']}{note}")
    if not (s["overdue"] or s["due_this_week"] or s["scheduled"]):
        lines.append("  Queue clear.")
    lines.append("")

    for title, items in (("📋 LORI", data["lori"]), ("🏠 HOUSE", data["house"])):
        lines.append(title)
        if not items:
            lines.append("  Nothing open.")
        for t in items[:6]:
            tag = ""
            if t["overdue"]:
                tag = "  ⚠ overdue"
            elif t["due_today"]:
                tag = "  due today"
            elif t["due_date"]:
                tag = f"  due {t['due_date'][5:]}"
            if t["recur"]:
                tag += f"  (↻ {t['recur']})"
            lines.append(f"  • {t['text']}{tag}")
        lines.append("")

    lines.append("🎯 TODAY'S FOCUS")
    lines.append(f"  {data['focus']}")
    return "\n".join(lines)
