"""Patient lookup pre-fills the review form from the hospital record; it never invents data."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.stewardship import config
from backend.stewardship.api import create_app
from backend.stewardship.records import JsonPatientRecords


def write(tmp_path, records):
    path = tmp_path / "patients.json"
    path.write_text(json.dumps({"records": records}))
    return path


def test_demo_records_load_and_include_cultures():
    records = JsonPatientRecords.load(config.PATIENT_RECORDS_JSON)
    record = records.get("SYN-DEMO-04")
    assert record.patient.age_years == 29
    assert record.cultures[0].isolates[0].organism == "Escherichia coli"
    assert record.source == "patients.json"


def test_missing_values_stay_missing():
    record = JsonPatientRecords.load(config.PATIENT_RECORDS_JSON).get("SYN-DEMO-05")
    assert record.patient.serum_creatinine_mg_dl is None
    assert record.patient.allergy_status == "UNKNOWN"


def test_unknown_patient_is_none_and_missing_file_is_empty(tmp_path):
    assert JsonPatientRecords.load(config.PATIENT_RECORDS_JSON).get("nobody") is None
    assert JsonPatientRecords.load(tmp_path / "absent.json").get("SYN-DEMO-01") is None


def test_duplicate_patient_id_is_rejected(tmp_path):
    patient = {"id": "p1", "age_years": 40, "sex": "M", "allergy_status": "NONE_KNOWN"}
    path = write(tmp_path, [{"patient": patient}, {"patient": patient}])
    with pytest.raises(ValueError, match="appears twice"):
        JsonPatientRecords.load(path)


def test_api_returns_record_or_404():
    # The lookup does not touch the stewardship service.
    client = TestClient(create_app(service=object()))
    response = client.get("/api/patients/SYN-DEMO-01")
    assert response.status_code == 200
    assert response.json()["patient"]["serum_creatinine_mg_dl"] == 0.8
    missing = client.get("/api/patients/nobody")
    assert missing.status_code == 404
    assert "Enter the details by hand" in missing.json()["detail"]
