"""Projects + Diary API."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DiaryEntry, Domain, Project

router = APIRouter(prefix="/api", tags=["projects"])

_HEX_RE = re.compile(r'^#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$')


def _validate_color(color: str | None) -> str | None:
    if color is None:
        return None
    if not _HEX_RE.match(color):
        raise HTTPException(400, "accent_color must be a valid hex color (#RGB or #RRGGBB)")
    return color


def project_payload(p: Project, entry_count: int) -> dict:
    return {
        "id": p.id, "key": p.key, "name": p.name,
        "domain_id": p.domain_id,
        "domain_key": p.domain.key if p.domain else None,
        "accent_color": p.accent_color, "note": p.note,
        "status": p.status, "sort_order": p.sort_order,
        "category": (getattr(p, "category", None) or "WORK"),
        "check_in_days": (getattr(p, "check_in_days", None) if getattr(p, "check_in_days", None) is not None else 14),
        "goal_pct": getattr(p, "goal_pct", 0) or 0,
        "entry_count": entry_count,
    }


class ProjectCreate(BaseModel):
    name: str
    domain_key: str | None = None
    accent_color: str = "#FF8800"
    note: str = ""
    category: str = "WORK"
    check_in_days: int = 14
    goal_pct: int = 0


class ProjectPatch(BaseModel):
    name: str | None = None
    domain_key: str | None = None
    accent_color: str | None = None
    note: str | None = None
    status: str | None = None
    sort_order: int | None = None
    category: str | None = None
    check_in_days: int | None = None
    goal_pct: int | None = None


class EntryCreate(BaseModel):
    text: str


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    counts = dict(
        db.query(DiaryEntry.project_id, func.count(DiaryEntry.id))
        .group_by(DiaryEntry.project_id).all()
    )
    projects = (db.query(Project)
                .filter(Project.status != "DELETED")
                .order_by(Project.sort_order).all())
    return [project_payload(p, counts.get(p.id, 0)) for p in projects]


@router.post("/projects")
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    key = name.lower().replace(" ", "-")
    if db.query(Project).filter(Project.key == key).first():
        raise HTTPException(409, f"project {key} already exists")
    domain_id = None
    if body.domain_key:
        d = db.query(Domain).filter(Domain.key == body.domain_key.upper()).first()
        if not d:
            raise HTTPException(404, f"unknown domain {body.domain_key}")
        domain_id = d.id
    category = body.category if body.category in ("WORK", "RESEARCH", "BACKLOG") else "WORK"
    p = Project(key=key, name=name, domain_id=domain_id,
                accent_color=_validate_color(body.accent_color), note=body.note,
                category=category, check_in_days=body.check_in_days,
                goal_pct=body.goal_pct,
                sort_order=db.query(Project).count())
    db.add(p)
    db.commit()
    return project_payload(p, 0)


@router.patch("/projects/{project_id}")
def patch_project(project_id: int, body: ProjectPatch, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "project not found")
    if body.status is not None and body.status not in ("ACTIVE", "PAUSED", "DONE", "DELETED"):
        raise HTTPException(400, "status must be ACTIVE/PAUSED/DONE/DELETED")
    if body.accent_color is not None:
        body.accent_color = _validate_color(body.accent_color)
    if body.domain_key is not None:
        d = db.query(Domain).filter(Domain.key == body.domain_key.upper()).first()
        if not d:
            raise HTTPException(404, f"unknown domain {body.domain_key}")
        p.domain_id = d.id
    for field in ("name", "accent_color", "note", "status", "sort_order", "category", "check_in_days", "goal_pct"):
        v = getattr(body, field)
        if v is not None:
            setattr(p, field, v)
    db.commit()
    count = db.query(DiaryEntry).filter(DiaryEntry.project_id == p.id).count()
    return project_payload(p, count)


@router.get("/diary/search")
def search_entries(q: str, db: Session = Depends(get_db)):
    q = q.strip()
    if not q:
        return []
    rows = (db.query(DiaryEntry).join(Project)
            .filter(DiaryEntry.text.ilike(f"%{q}%"))
            .order_by(DiaryEntry.created_at.desc()).limit(50).all())
    return [{
        "id": e.id, "project_id": e.project_id, "project_name": e.project.name,
        "created_at": e.created_at.isoformat(), "text": e.text,
    } for e in rows]


@router.get("/diary/{project_id}")
def list_entries(project_id: int, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    rows = (db.query(DiaryEntry)
            .filter(DiaryEntry.project_id == project_id)
            .order_by(DiaryEntry.created_at.desc()).all())
    return [{"id": e.id, "created_at": e.created_at.isoformat(), "text": e.text}
            for e in rows]


@router.post("/diary/{project_id}")
def add_entry(project_id: int, body: EntryCreate, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "project not found")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text required")
    e = DiaryEntry(project_id=project_id, text=text)
    db.add(e)
    db.commit()
    return {"id": e.id, "created_at": e.created_at.isoformat(), "text": e.text}
