import pytest

from backend.stewardship.intake import patient_identity


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Patient: Synthetic Patient 01\nPatient ID: SYN-DEMO-01\nAge: 42", ("SYN-DEMO-01", "Synthetic Patient 01")),
        ("Patient: Synthetic Patient 01   Patient ID: SYN-DEMO-01", ("SYN-DEMO-01", "Synthetic Patient 01")),
        ("Name: Ravi Kumar\nUHID: 88231", ("88231", "Ravi Kumar")),
        ("Patient ID: SYN-DEMO-04", ("SYN-DEMO-04", None)),
        ("Patient setting: OPD\nAge: 30", (None, None)),
    ],
)
def test_patient_identity_reads_only_what_is_printed(text, expected):
    assert patient_identity(text) == expected
