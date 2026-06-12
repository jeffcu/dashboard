"""Daily Log + Domains API."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DailyLog, Domain

router = APIRouter(prefix="/api", tags=["log"])


def week_start(offset: int = 0) -> date:
    """Monday of the week `offset` weeks from current."""
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=offset)


def domain_payload(d: Domain) -> dict:
    return {
        "id": d.id, "key": d.key, "label": d.label,
        "weekly_goal": d.weekly_goal, "sort_order": d.sort_order,
        "active": d.active,
    }


# ── Domains ──────────────────────────────────────────────

class DomainCreate(BaseModel):
    key: str
    label: str
    weekly_goal: int = 0


class DomainPatch(BaseModel):
    label: str | None = None
    weekly_goal: int | None = None
    sort_order: int | None = None
    active: bool | None = None


@router.get("/domains")
def list_domains(db: Session = Depends(get_db)):
    domains = db.query(Domain).order_by(Domain.sort_order).all()
    return [domain_payload(d) for d in domains]


@router.post("/domains")
def create_domain(body: DomainCreate, db: Session = Depends(get_db)):
    key = body.key.strip().upper()
    if not key:
        raise HTTPException(400, "key required")
    if db.query(Domain).filter(Domain.key == key).first():
        raise HTTPException(409, f"domain {key} already exists")
    max_order = db.query(Domain).count()
    d = Domain(key=key, label=body.label.strip() or key.title(),
               weekly_goal=body.weekly_goal, sort_order=max_order)
    db.add(d)
    db.commit()
    return domain_payload(d)


@router.patch("/domains/{domain_id}")
def patch_domain(domain_id: int, body: DomainPatch, db: Session = Depends(get_db)):
    d = db.get(Domain, domain_id)
    if not d:
        raise HTTPException(404, "domain not found")
    for field in ("label", "weekly_goal", "sort_order", "active"):
        v = getattr(body, field)
        if v is not None:
            setattr(d, field, v)
    db.commit()
    return domain_payload(d)


# ── Daily log ────────────────────────────────────────────

class LogUpsert(BaseModel):
    date: date
    domain_key: str
    hours: int


@router.get("/log/week")
def get_week(offset: int = 0, db: Session = Depends(get_db)):
    start = week_start(offset)
    days = [start + timedelta(days=i) for i in range(7)]
    domains = (db.query(Domain).filter(Domain.active == True)  # noqa: E712
               .order_by(Domain.sort_order).all())
    rows = (db.query(DailyLog)
            .filter(DailyLog.date >= start, DailyLog.date <= days[-1]).all())
    by_id = {d.id: d.key for d in domains}
    cells = {}
    for r in rows:
        key = by_id.get(r.domain_id)
        if key and r.hours > 0:
            cells[f"{r.date.isoformat()}_{key}"] = r.hours
    col_totals = {d.key: 0 for d in domains}
    for r in rows:
        key = by_id.get(r.domain_id)
        if key:
            col_totals[key] += r.hours
    return {
        "week_start": start.isoformat(),
        "days": [d.isoformat() for d in days],
        "today": date.today().isoformat(),
        "domains": [domain_payload(d) for d in domains],
        "cells": cells,
        "col_totals": col_totals,
        "week_total": sum(col_totals.values()),
    }


@router.post("/log")
def upsert_log(body: LogUpsert, db: Session = Depends(get_db)):
    domain = db.query(Domain).filter(Domain.key == body.domain_key.upper()).first()
    if not domain:
        raise HTTPException(404, f"unknown domain {body.domain_key}")
    hours = max(0, min(8, body.hours))
    row = (db.query(DailyLog)
           .filter(DailyLog.date == body.date, DailyLog.domain_id == domain.id)
           .first())
    if row:
        if hours == 0:
            db.delete(row)
        else:
            row.hours = hours
    elif hours > 0:
        db.add(DailyLog(date=body.date, domain_id=domain.id, hours=hours))
    db.commit()
    return {"date": body.date.isoformat(), "domain_key": domain.key, "hours": hours}


@router.get("/log/trends")
def get_trends(weeks: int = 8, db: Session = Depends(get_db)):
    weeks = max(1, min(26, weeks))
    start = week_start(-(weeks - 1))
    domains = (db.query(Domain).filter(Domain.active == True)  # noqa: E712
               .order_by(Domain.sort_order).all())
    rows = db.query(DailyLog).filter(DailyLog.date >= start).all()
    by_id = {d.id: d.key for d in domains}

    # weekly totals per domain
    totals = {d.key: [0] * weeks for d in domains}
    for r in rows:
        key = by_id.get(r.domain_id)
        if not key:
            continue
        idx = (r.date - start).days // 7
        if 0 <= idx < weeks:
            totals[key][idx] += r.hours

    result = []
    for d in domains:
        series = totals[d.key]
        # streak: consecutive weeks (ending now) with >=1h
        streak = 0
        for v in reversed(series):
            if v >= 1:
                streak += 1
            else:
                break
        result.append({
            "key": d.key, "label": d.label, "weekly_goal": d.weekly_goal,
            "weeks": series, "streak": streak,
            "dormant": sum(series[-2:]) == 0,  # zero hours last 2 weeks
        })
    return {"weeks": weeks, "week_start": start.isoformat(), "domains": result}
