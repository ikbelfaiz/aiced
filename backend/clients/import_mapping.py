"""Approved positional rules for a future published-import projection.

This module does not read snapshots or write client records. Callers must enforce
publication, provenance, permissions and transactional idempotency independently.
"""
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class PhysicalSource:
    source_id: str
    last_name: str | None
    first_name: str | None
    full_name: str | None
    birth_date: date | None
    email: str | None
    phone: str | None
    mobile: str | None


def _text(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Une valeur texte source est invalide.")
    return value if value.strip() else None


def physical_source(cells, normalized_dates):
    """Read approved positions without interpreting another identifier as B."""
    source_id = _text(cells.get('2'))
    if not source_id or source_id != source_id.strip() or len(source_id) > 160:
        raise ValueError("Identifiant source physique invalide.")
    raw_date = normalized_dates.get('9')
    birth_date = (datetime.fromisoformat(raw_date).date() if 'T' in raw_date else date.fromisoformat(raw_date)) if raw_date else None
    return PhysicalSource(source_id, _text(cells.get('3')), _text(cells.get('4')),
                          _text(cells.get('5')), birth_date, _text(cells.get('15')),
                          _text(cells.get('12')), _text(cells.get('13')))


def nonempty_contact_updates(source):
    """An empty source value must not erase the current editable CRM value.

    The CRM has one phone field: use the source telephone when present, then
    mobile as a fallback. No account contact is promoted to its holder here.
    """
    updates = {}
    if source.email is not None:
        updates['email'] = source.email
    if source.phone or source.mobile:
        updates['phone'] = source.phone or source.mobile
    return updates


def physical_account_holder(cells):
    """Extract the physical-holder key; lookup must be organization scoped."""
    holder = _text(cells.get('4'))
    if not holder or holder != holder.strip() or len(holder) > 160:
        raise ValueError("Identifiant de détenteur invalide.")
    return holder
