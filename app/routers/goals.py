"""Goals API — % of time per domain vs targets. Project hours roll up to domain totals."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DailyLog, Domain, Project, ProjectLog

router = APIRouter(prefix="/api", tags=["goals"])


@router.get("/goals")
def get_goals(db: Session = Depends(get_db)):
    today = date.today()

    # date ranges
    wk_start = today - timedelta(days=today.weekday())
    mo_start = today.replace(day=1)
    overall_start = wk_start - timedelta(weeks=7)   # 8 weeks rolling

    domains = (db.query(Domain).filter(Domain.active == True)   # noqa: E712
               .order_by(Domain.sort_order).all())
    by_id = {d.id: d.key for d in domains}

    # Domain-level logs
    all_rows = db.query(DailyLog).filter(DailyLog.date >= overall_start).all()

    wk: dict[str, int] = {d.key: 0 for d in domains}
    mo: dict[str, int] = {d.key: 0 for d in domains}
    ov: dict[str, int] = {d.key: 0 for d in domains}

    for r in all_rows:
        k = by_id.get(r.domain_id)
        if not k:
            continue
        if r.date >= wk_start:
            wk[k] += r.hours
        if r.date >= mo_start:
            mo[k] += r.hours
        ov[k] += r.hours

    # Roll up project_log hours into domain totals
    proj_rows = (db.query(ProjectLog)
                 .filter(ProjectLog.date >= overall_start).all())
    dom_by_proj: dict[int, str] = {}
    for p in db.query(Project).filter(Project.domain_id.isnot(None)).all():
        k = by_id.get(p.domain_id)
        if k:
            dom_by_proj[p.id] = k
    for r in proj_rows:
        k = dom_by_proj.get(r.project_id)
        if not k:
            continue
        if r.date >= wk_start:
            wk[k] += r.hours
        if r.date >= mo_start:
            mo[k] += r.hours
        ov[k] += r.hours

    wk_total = max(sum(wk.values()), 1)
    mo_total = max(sum(mo.values()), 1)
    ov_total = max(sum(ov.values()), 1)

    domain_stats = []
    for d in domains:
        goal_pct = getattr(d, "goal_pct", 0) or 0
        week_pct  = round(wk[d.key] / wk_total * 100)
        month_pct = round(mo[d.key] / mo_total * 100)
        overall_pct = round(ov[d.key] / ov_total * 100)
        gap = (week_pct - goal_pct) if goal_pct > 0 else None   # negative = under
        domain_stats.append({
            "id": d.id,
            "key": d.key,
            "label": d.label,
            "goal_pct": goal_pct,
            "week_pct": week_pct,
            "month_pct": month_pct,
            "overall_pct": overall_pct,
            "week_hours": wk[d.key],
            "month_hours": mo[d.key],
            "overall_hours": ov[d.key],
            "gap": gap,        # negative = underperforming
        })

    # Top 5 underperforming domains (those with a goal set)
    underperformers = sorted(
        [{"kind": "domain", **s} for s in domain_stats if s["goal_pct"] > 0 and s["gap"] is not None],
        key=lambda x: x["gap"]
    )[:5]

    return {
        "domain_stats": domain_stats,
        "underperformers": underperformers,
        "totals": {
            "week_hours": sum(wk.values()),
            "month_hours": sum(mo.values()),
            "overall_hours": ov_total,
        },
    }
