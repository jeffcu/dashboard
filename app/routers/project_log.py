"""Project-level time tracking — stores hours per project per day.
Domain totals roll up from here automatically via /api/log/week.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Domain, Project, ProjectLog

router = APIRouter(prefix="/api", tags=["project_log"])


def week_start(offset: int = 0) -> date:
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


class ProjLogUpsert(BaseModel):
    date: date
    project_id: int
    hours: int


@router.get("/project-log/week")
def get_project_week(offset: int = 0, db: Session = Depends(get_db)):
    """
    Returns all active (non-DELETED) projects with their hours for the requested week,
    grouped into PRIORITIES / RESEARCH / BACKLOG sections.
    """
    start = week_start(offset)
    days = [start + timedelta(days=i) for i in range(7)]

    # Load active projects (not DELETED) joined with domain
    proj_list = (
        db.query(Project)
        .filter(Project.status != "DELETED")
        .order_by(Project.sort_order)
        .all()
    )

    # Load all domains for colour/label lookup
    domains = {d.id: d for d in db.query(Domain).all()}

    # Load project_log for this week
    rows = (
        db.query(ProjectLog)
        .filter(ProjectLog.date >= start, ProjectLog.date <= days[-1])
        .all()
    )
    cells: dict[str, int] = {}
    for r in rows:
        if r.hours > 0:
            cells[f"{r.date.isoformat()}_{r.project_id}"] = r.hours

    proj_totals: dict[int, int] = {}
    for r in rows:
        proj_totals[r.project_id] = proj_totals.get(r.project_id, 0) + r.hours

    # All-time cumulative totals
    all_time_rows = db.query(ProjectLog).all()
    all_time: dict[int, int] = {}
    for r in all_time_rows:
        all_time[r.project_id] = all_time.get(r.project_id, 0) + r.hours

    # ordered domain list for JS grouping
    ordered_domains = sorted(domains.values(), key=lambda d: d.sort_order)
    # domain all-time hours from project_log
    dom_proj_all: dict[int, int] = {}
    for p in proj_list:
        if p.domain_id:
            dom_proj_all[p.domain_id] = dom_proj_all.get(p.domain_id, 0) + all_time.get(p.id, 0)

    domain_list = [
        {"id": d.id, "key": d.key, "label": d.label, "sort_order": d.sort_order,
         "active": d.active, "all_time_hours": dom_proj_all.get(d.id, 0),
         "weekly_goal": d.weekly_goal, "goal_pct": getattr(d, "goal_pct", 0) or 0}
        for d in ordered_domains if d.active
    ]
    # unassigned domain placeholder
    domain_list.append({"id": None, "key": None, "label": "Unassigned", "sort_order": 9999, "active": True})

    def proj_payload(p: Project) -> dict:
        dom = domains.get(p.domain_id) if p.domain_id else None
        cat = getattr(p, "category", "WORK") or "WORK"
        return {
            "id": p.id,
            "name": p.name,
            "domain_key": dom.key if dom else None,
            "domain_label": dom.label if dom else None,
            "domain_sort": dom.sort_order if dom else 9999,
            "accent_color": p.accent_color,
            "category": cat,
            "status": p.status,
            "week_hours": proj_totals.get(p.id, 0),
            "all_time_hours": all_time.get(p.id, 0),
        }

    all_projects = [proj_payload(p) for p in proj_list]

    return {
        "week_start": start.isoformat(),
        "days": [d.isoformat() for d in days],
        "today": date.today().isoformat(),
        "domains": domain_list,
        "projects": all_projects,
        "cells": cells,
        "week_total": sum(proj_totals.values()),
    }


@router.post("/project-log")
def upsert_project_log(body: ProjLogUpsert, db: Session = Depends(get_db)):
    proj = db.get(Project, body.project_id)
    if not proj:
        raise HTTPException(404, "project not found")
    hours = max(0, min(8, body.hours))
    row = (
        db.query(ProjectLog)
        .filter(ProjectLog.date == body.date, ProjectLog.project_id == body.project_id)
        .first()
    )
    if row:
        if hours == 0:
            db.delete(row)
        else:
            row.hours = hours
    elif hours > 0:
        db.add(ProjectLog(date=body.date, project_id=body.project_id, hours=hours))
    db.commit()
    return {"date": body.date.isoformat(), "project_id": body.project_id, "hours": hours}
