"""Agenda engine — one source of truth for the TODAY dashboard, the Telegram
daily brief, and the focus suggestion.

Answers Jeff's standing question every morning:
  "Here's the priorities and the projects getting behind —
   that's my agenda to keep my mind moving forward and challenged."
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import DailyLog, DiaryEntry, Domain, Friend, Project, Todo
from .routers.social import next_action

STALE_PROJECT_DAYS = 14  # ACTIVE project with no diary entry for this long = getting behind


def _week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def build_brief_data(db: Session) -> dict:
    today = date.today()
    start = _week_start()
    week_end = today + timedelta(days=6 - today.weekday())

    # ── time investment ──────────────────────────────────
    domains = (db.query(Domain).filter(Domain.active == True)  # noqa: E712
               .order_by(Domain.sort_order).all())
    by_id = {d.id: d.key for d in domains}

    rows = db.query(DailyLog).filter(DailyLog.date >= start).all()
    week = {d.key: 0 for d in domains}
    for r in rows:
        k = by_id.get(r.domain_id)
        if k:
            week[k] += r.hours

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
        "behind_goal": bool(d.weekly_goal and week[d.key] < d.weekly_goal),
    } for d in domains]

    # ── projects getting behind ──────────────────────────
    last_entry = dict(
        db.query(DiaryEntry.project_id, func.max(DiaryEntry.created_at))
        .group_by(DiaryEntry.project_id).all())
    stale_projects = []
    for p in db.query(Project).filter(Project.status == "ACTIVE").all():
        last = last_entry.get(p.id) or p.created_at
        days = (datetime.now() - last).days
        if days >= STALE_PROJECT_DAYS:
            stale_projects.append({
                "id": p.id, "name": p.name,
                "domain_key": p.domain.key if p.domain else None,
                "days_quiet": days,
            })
    stale_projects.sort(key=lambda x: -x["days_quiet"])

    # ── social CRM: steps due ────────────────────────────
    friends = db.query(Friend).filter(Friend.active == True).all()  # noqa: E712
    overdue = sorted(
        [f for f in friends
         if f.phase == "TO_SCHEDULE" and f.due_date and f.due_date < today],
        key=lambda f: f.due_date)
    due_week = [f for f in friends
                if f.phase == "TO_SCHEDULE" and f.due_date
                and today <= f.due_date <= week_end]
    scheduled = [f for f in friends if f.phase == "SCHEDULED"]

    def social_step(f: Friend) -> dict:
        od = (today - f.due_date).days if (f.due_date and f.due_date < today
                                           and f.phase == "TO_SCHEDULE") else None
        return {"name": f.name, "days": od,
                "due_date": f.due_date.isoformat() if f.due_date else None,
                "note": f.static_note,
                "next_action": next_action(f, od)}

    # ── Lori's Priorities ────────────────────────────────
    pri_items = (db.query(Todo)
                 .filter(Todo.list_id == "lori", Todo.active == True,  # noqa: E712
                         Todo.done == False).all())  # noqa: E712
    pri_items.sort(key=lambda t: t.sort_order)
    priorities = [{
        "id": t.id, "text": t.text, "rank": i + 1,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "overdue": bool(t.due_date and t.due_date < today),
        "due_today": t.due_date == today,
        "recur": t.recur_type if t.recur_type != "none" else None,
    } for i, t in enumerate(pri_items)]

    # ── the agenda: ordered, actionable, challenging ─────
    agenda = []
    for f in overdue:
        agenda.append({"kind": "social", "urgency": "overdue",
                       "text": f"{next_action(f, (today - f.due_date).days)['text']} — {f.name}"})
    for p_ in priorities:
        if p_["overdue"]:
            agenda.append({"kind": "priority", "urgency": "overdue",
                           "text": f"Priority slipping: {p_['text']}"})
    for p_ in priorities:
        if p_["due_today"]:
            agenda.append({"kind": "priority", "urgency": "today",
                           "text": f"Due today: {p_['text']}"})
    for f in scheduled:
        note = f" — {f.static_note}" if f.static_note else ""
        agenda.append({"kind": "social", "urgency": "scheduled",
                       "text": f"On the books: {f.name}{note}"})
    behind = sorted([dl for dl in domain_lines if dl["behind_goal"]],
                    key=lambda x: x["hours"] - x["goal"])
    for dl in behind:
        agenda.append({"kind": "domain", "urgency": "behind",
                       "text": f"{dl['key']}: {dl['hours']}h of {dl['goal']}h weekly goal"})
    for sp in stale_projects[:3]:
        agenda.append({"kind": "project", "urgency": "stale",
                       "text": f"{sp['name']} has been quiet {sp['days_quiet']}d — touch it today"})
    for dl in domain_lines:
        if dl["dormant"] and not dl["behind_goal"]:
            agenda.append({"kind": "domain", "urgency": "dormant",
                           "text": f"{dl['key']} dormant 3+ weeks — still part of the plan?"})

    # ── today's focus = top of the agenda ────────────────
    focus = agenda[0]["text"] if agenda else "All wheels turning — pick something fun"

    return {
        "date": today.isoformat(),
        "domains": domain_lines,
        "week_total": sum(week.values()),
        "focus": focus,
        "agenda": agenda,
        "priorities": priorities,
        "stale_projects": stale_projects,
        "social": {
            "overdue": [social_step(f) for f in overdue],
            "due_this_week": [social_step(f) for f in due_week],
            "scheduled": [social_step(f) for f in scheduled],
        },
    }


def _bar(hours: int, goal: int) -> str:
    width = max(goal, hours, 6)
    filled = min(hours, width)
    return "█" * filled + "░" * (width - filled)


def format_brief_text(data: dict) -> str:
    d = datetime.fromisoformat(data["date"])
    lines = [f"📅 DAILY BRIEF — {d.strftime('%A %b %-d')}", ""]

    lines.append("🎯 TODAY'S FOCUS")
    lines.append(f"  {data['focus']}")
    lines.append("")

    if data["agenda"]:
        lines.append("📌 AGENDA")
        for item in data["agenda"][:7]:
            mark = {"overdue": "🔴", "today": "🟠", "scheduled": "✅",
                    "behind": "⏱", "stale": "💡", "dormant": "⚠"}.get(item["urgency"], "•")
            lines.append(f"  {mark} {item['text']}")
        lines.append("")

    lines.append("⏱ THIS WEEK SO FAR")
    for dom in data["domains"]:
        goal = f" / {dom['goal']}h goal" if dom["goal"] else ""
        warn = "  ⚠ no log 3+ weeks" if dom["dormant"] else ""
        lines.append(f"  {dom['key']:<7}{_bar(dom['hours'], dom['goal'])} "
                     f"{dom['hours']}h{goal}{warn}")
    lines.append("")

    s = data["social"]
    lines.append("📞 SOCIAL — STEPS DUE")
    for o in s["overdue"]:
        lines.append(f"  🔴 {o['name']}: {o['next_action']['text']}")
    for o in s["due_this_week"]:
        lines.append(f"  📅 {o['name']}: {o['next_action']['text']}")
    for o in s["scheduled"]:
        lines.append(f"  ✅ {o['name']}: {o['next_action']['text']}")
    if not (s["overdue"] or s["due_this_week"] or s["scheduled"]):
        lines.append("  Queue clear — all relationships on plan.")
    lines.append("")

    lines.append("📋 LORI'S PRIORITIES")
    if not data["priorities"]:
        lines.append("  Nothing open.")
    for t in data["priorities"][:6]:
        tag = ""
        if t["overdue"]:
            tag = "  ⚠ overdue"
        elif t["due_today"]:
            tag = "  due today"
        elif t["due_date"]:
            tag = f"  due {t['due_date'][5:]}"
        if t["recur"]:
            tag += f"  (↻ {t['recur']})"
        lines.append(f"  {t['rank']}. {t['text']}{tag}")

    return "\n".join(lines)
