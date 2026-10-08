"""Patient lookup: fetch what the hospital already knows about a patient by ID, so the
reviewer does not retype it.

A record only pre-fills the review form. It decides nothing: the reviewer sees every value,
can change it, and still selects the syndrome and enters the prescription. A field the record
lacks stays empty, and the rules answer CANNOT_ASSESS for it as they would for typed input.

The demo reads a JSON file of synthetic patients. A real deployment replaces JsonPatientRecords
with an adapter for the hospital system (for example FHIR Patient, Observation and
AllergyIntolerance) that returns the same PatientRecord.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .intake import CultureInput
from .schemas import Patient


class PatientRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    patient: Patient
    cultures: tuple[CultureInput, ...] = ()
    source: str


class JsonPatientRecords:
    """Patient records from a JSON file: {"records": [{"patient": {...}, "cultures": [...]}]}."""

    def __init__(self, records: dict[str, PatientRecord]):
        self._records = records

    @classmethod
    def load(cls, path: Path) -> "JsonPatientRecords":
        if not path.exists():
            return cls({})
        source = path.name
        records = {}
        for item in json.loads(path.read_text(encoding="utf-8"))["records"]:
            record = PatientRecord(source=source, **item)
            if record.patient.id in records:
                raise ValueError(f"{path}: patient '{record.patient.id}' appears twice.")
            records[record.patient.id] = record
        return cls(records)

    def get(self, patient_id: str) -> PatientRecord | None:
        return self._records.get(patient_id.strip())
