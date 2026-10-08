"""Append-only audit trail of decisions.

Entries are only ever appended, never edited or deleted, so the log shows who decided what
and when. The JSON-lines file is the hackathon store; a database table can implement the same
protocol later.
"""

from pathlib import Path
from typing import Protocol

from .schemas import AuditEntry


class AuditLog(Protocol):
    def append(self, entry: AuditEntry) -> None: ...

    def list(self, entity_id: str | None = None) -> list[AuditEntry]: ...


class JsonlAuditLog:
    """Audit log stored as one JSON object per line."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: AuditEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    def list(self, entity_id: str | None = None) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            entries = [AuditEntry.model_validate_json(line) for line in f if line.strip()]
        return [e for e in entries if entity_id is None or e.entity_id == entity_id]
