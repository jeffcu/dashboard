"""ORM table definitions — per REQUIREMENTS.md data models."""
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Domain(Base):
    __tablename__ = "domains"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    weekly_goal: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class DailyLog(Base):
    __tablename__ = "daily_log"
    __table_args__ = (UniqueConstraint("date", "domain_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), nullable=False)
    hours: Mapped[int] = mapped_column(Integer, default=0)

    domain: Mapped[Domain] = relationship()


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("domains.id"), nullable=True)
    accent_color: Mapped[str] = mapped_column(String, default="#FF8800")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="ACTIVE")  # ACTIVE/PAUSED/DONE
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    domain: Mapped[Domain | None] = relationship()
    entries: Mapped[list["DiaryEntry"]] = relationship(back_populates="project")


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped[Project] = relationship(back_populates="entries")


class Friend(Base):
    __tablename__ = "friends"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, default="PHONE")  # PHONE/LOCAL
    phase: Mapped[str] = mapped_column(String, default="TO_SCHEDULE")  # TO_SCHEDULE/SCHEDULED/DONE
    static_note: Mapped[str] = mapped_column(Text, default="")
    cadence_days: Mapped[int] = mapped_column(Integer, default=30)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    history: Mapped[list["ContactHistory"]] = relationship(back_populates="friend")


class ContactHistory(Base):
    __tablename__ = "contact_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    friend_id: Mapped[int] = mapped_column(ForeignKey("friends.id"), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # SCHEDULED/DONE/RESET
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    friend: Mapped[Friend] = relationship(back_populates="history")


class Todo(Base):
    __tablename__ = "todos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[str] = mapped_column(String, nullable=False)  # 'lori' / 'house'
    text: Mapped[str] = mapped_column(Text, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    recur_type: Mapped[str] = mapped_column(String, default="none")  # none/weekly/monthly/custom
    recur_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # manual priority order
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
