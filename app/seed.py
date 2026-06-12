"""Seed default domains, friends, and projects on first run (empty tables only)."""
from sqlalchemy.orm import Session

from .models import Domain, Friend, Project

DEFAULT_DOMAINS = [
    ("CODING", "Coding"), ("ROBOT", "Robot"), ("ART", "Art"), ("MTB", "Mtb"),
    ("SOCIAL", "Social"), ("CIVIC", "Civic"), ("FIN", "Fin"), ("GAMING", "Gaming"),
    ("LORI", "Lori"), ("HOUSE", "House"),
]

DEFAULT_FRIENDS = [
    ("Mitch", "LOCAL", "SCHEDULED", "Lunch this week · Jun 14"),
    ("Greg", "PHONE", "TO_SCHEDULE", ""),
    ("Alan", "PHONE", "TO_SCHEDULE", "Call next Tuesday Jun 17"),
    ("Steve", "PHONE", "TO_SCHEDULE", ""),
    ("Michael", "PHONE", "TO_SCHEDULE", ""),
    ("Andy", "LOCAL", "TO_SCHEDULE", ""),
    ("Thad", "PHONE", "TO_SCHEDULE", ""),
    ("Flagg", "PHONE", "TO_SCHEDULE", ""),
    ("Placido", "PHONE", "TO_SCHEDULE", ""),
    ("Dave", "LOCAL", "TO_SCHEDULE", ""),
    ("Ron", "PHONE", "TO_SCHEDULE", ""),
    ("Sheldone", "PHONE", "TO_SCHEDULE", ""),
]

# (key, name, domain_key, accent_color, note) — colors match Workshop UI palette
DEFAULT_PROJECTS = [
    ("nocturne", "Nocturne", "ART", "#C44A18", "Oil · en plein air"),
    ("sculpture", "Sculpture", "ART", "#C44A18", "Plasticene · David ref"),
    ("trust", "Trust", "CODING", "#1E6E62", "Running"),
    ("intel", "Intelligence", "CODING", "#1E6E62", "RSS pipeline"),
    ("dnd", "D&D Server", "CODING", "#1E6E62", "Local · Portainer"),
    ("robot", "Robot", "ROBOT", "#3A6EA5", "Code lab · starting"),
    ("ocparks", "OC Parks", "CIVIC", "#B07D10", "E-bike campaign"),
    ("finance", "Planning", "FIN", "#8A5A2B", "Roth + Scholarship"),
]


def seed(db: Session) -> None:
    if db.query(Domain).count() == 0:
        for i, (key, label) in enumerate(DEFAULT_DOMAINS):
            db.add(Domain(key=key, label=label, sort_order=i))
        db.commit()

    if db.query(Friend).count() == 0:
        for name, type_, phase, note in DEFAULT_FRIENDS:
            db.add(Friend(name=name, type=type_, phase=phase, static_note=note))
        db.commit()

    if db.query(Project).count() == 0:
        domains = {d.key: d.id for d in db.query(Domain).all()}
        for i, (key, name, dkey, color, note) in enumerate(DEFAULT_PROJECTS):
            db.add(Project(
                key=key, name=name, domain_id=domains.get(dkey),
                accent_color=color, note=note, sort_order=i,
            ))
        db.commit()
