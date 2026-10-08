"""SYNTHETIC DEMO DATA: the single source of the demo cases.

Run from the repository root:
    python data/demo_synthetic/build_cases.py   # writes cases, prescriptions, patients .json
    python data/demo_synthetic/make_images.py     # checks the text, then draws images/

Each case is a full prescription as a doctor writes it: patient details, the diagnosis, every
medicine (antibiotics and the rest), investigations and culture results. The expected findings
in cases.json are what the engine returns for the case when this script runs; read them before
committing, they are not checked against anything else here.
"""

import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

LABEL = (
    "SYNTHETIC / DEMO DATA. Invented patients, fictional hospital and doctor. "
    "Not real patient data."
)
PAGE = {
    "header": [
        "SYNTHETIC DEMO TEACHING HOSPITAL (FICTIONAL)",
        "Department of General Medicine - Prescription",
    ],
    "footer": [
        "Signature: Dr. Demo Physician (fictional)",
        "SYNTHETIC DEMO DATA - not a real patient, doctor or prescription",
    ],
}
SETTING_TEXT = {"OPD": "OPD", "WARD": "Inpatient ward", "ICU": "ICU"}


@dataclass
class Case:
    id: str
    slug: str
    demonstrates: str
    age: int
    sex: str
    setting: str
    diagnosis: str | None
    # (line as printed, (generic, dose_mg, freq_per_day, route, duration_days) it must parse to)
    meds: list[tuple[str, tuple]]
    weight: float | None = None
    creatinine: float | None = None
    allergy_status: str = "NONE_KNOWN"
    allergies: list[str] = field(default_factory=list)
    allergy_text: str | None = None
    cultures: list[dict] = field(default_factory=list)
    culture_lines: list[str] = field(default_factory=list)

    @property
    def patient(self) -> dict:
        return {
            "id": self.id,
            "age_years": self.age,
            "sex": self.sex,
            "weight_kg": self.weight,
            "serum_creatinine_mg_dl": self.creatinine,
            "allergy_status": self.allergy_status,
            "allergies": self.allergies,
        }

    @property
    def prescription_text(self) -> str:
        """What to paste as the typed prescription: the diagnosis line, then the medicines."""
        lines = [f"Diagnosis: {self.diagnosis}"] if self.diagnosis else []
        return "\n".join([*lines, "Rx", *(line for line, _ in self.meds)])

    def rows(self) -> list[list[str]]:
        allergy = self.allergy_text or {
            "NONE_KNOWN": "No known drug allergy",
            "UNKNOWN": "not recorded",
        }.get(self.allergy_status, ", ".join(self.allergies))
        weight = f"{self.weight:g} kg" if self.weight else "not recorded at this visit"
        creatinine = (
            f"serum creatinine {self.creatinine:g} mg/dL"
            if self.creatinine
            else "serum creatinine not available"
        )
        rows = [
            ["field", f"Patient: Synthetic Patient {self.id[-2:]}", f"Patient ID: {self.id}"],
            ["field", f"Age: {self.age} years", f"Sex: {'Female' if self.sex == 'F' else 'Male'}"],
            ["field", f"Weight: {weight}", f"Patient setting: {SETTING_TEXT[self.setting]}"],
            ["field", f"Allergies: {allergy}"],
            ["gap"],
        ]
        if self.diagnosis:
            rows.append(["field", f"Diagnosis: {self.diagnosis}"])
        rows += [["gap"], ["rx", "Rx"]]
        rows += [["med", f"{i}. {line}"] for i, (line, _) in enumerate(self.meds, start=1)]
        rows += [["gap"], ["field", f"Investigations: {creatinine}"]]
        rows += [["field", line] for line in self.culture_lines]
        return rows

    def expected_orders(self) -> list[dict]:
        keys = ("generic", "dose_mg", "freq_per_day", "route", "duration_days")
        return [dict(zip(keys, parsed, strict=True)) for _, parsed in self.meds]

    def request(self) -> dict:
        return {
            "patient": self.patient,
            "setting": self.setting,
            "diagnosis_text": self.diagnosis,
            "prescription": "\n".join(line for line, _ in self.meds),
            "cultures": self.cultures,
        }


def urine(organism: str | None, status: str = "FINAL", **sus: str) -> dict:
    isolates = [{"organism": organism, "susceptibilities": sus}] if organism else []
    return {"specimen_type": "urine", "status": status, "isolates": isolates}


PARA = ("Tab Paracetamol 650 mg PO TDS x 3 days", ("paracetamol", 650.0, 3.0, "PO", 3))
CAP_OPD = "Community-acquired pneumonia, OPD, without comorbidities"

CASES = [
    Case(
        "SYN-DEMO-01",
        "concordant",
        "Guideline-concordant: first-line drug, dose and duration",
        42,
        "F",
        "OPD",
        CAP_OPD,
        weight=62,
        creatinine=0.8,
        meds=[
            ("Cap Amoxicillin 1 g PO TDS x 5 days", ("amoxicillin", 1000.0, 3.0, "PO", 5)),
            PARA,
        ],
    ),
    Case(
        "SYN-DEMO-02",
        "wrong_antibiotic",
        "Drug not listed for the syndrome (R1) and a Watch drug where Access exists (R2)",
        35,
        "M",
        "OPD",
        CAP_OPD,
        weight=74,
        creatinine=0.9,
        meds=[
            ("Tab Ciprofloxacin 500 mg PO BD x 5 days", ("ciprofloxacin", 500.0, 2.0, "PO", 5)),
            PARA,
            ("Tab Ambroxol 30 mg PO TDS x 5 days", ("ambroxol", 30.0, 3.0, "PO", 5)),
        ],
    ),
    Case(
        "SYN-DEMO-03",
        "dose_duration",
        "Dose below the guideline (R3) and course too long (R5)",
        58,
        "M",
        "OPD",
        CAP_OPD,
        weight=80,
        creatinine=1.0,
        meds=[
            ("Cap Amoxicillin 500 mg PO TDS x 10 days", ("amoxicillin", 500.0, 3.0, "PO", 10)),
            PARA,
        ],
    ),
    Case(
        "SYN-DEMO-04",
        "culture_resistance",
        "Culture shows the organism is resistant (C3)",
        29,
        "F",
        "OPD",
        "Uncomplicated cystitis",
        weight=55,
        creatinine=0.7,
        meds=[
            ("Tab Nitrofurantoin 100 mg PO BD x 5 days", ("nitrofurantoin", 100.0, 2.0, "PO", 5)),
            ("Tab Paracetamol 500 mg PO TDS x 3 days", ("paracetamol", 500.0, 3.0, "PO", 3)),
        ],
        cultures=[urine("Escherichia coli", Nitrofurantoin="R", Cotrimoxazole="S")],
        culture_lines=[
            "Urine culture (final report): Escherichia coli",
            "Urine culture susceptibility: nitrofurantoin resistant (R)",
            "Urine culture susceptibility: cotrimoxazole susceptible (S)",
        ],
    ),
    Case(
        "SYN-DEMO-05",
        "missing_info",
        "Missing frequency, duration, weight, creatinine and allergy status",
        67,
        "M",
        "OPD",
        CAP_OPD,
        allergy_status="UNKNOWN",
        meds=[("Amoxicillin 1 g", ("amoxicillin", 1000.0, None, None, None))],
    ),
    Case(
        "SYN-DEMO-06",
        "renal_impairment",
        "Dose too high for the kidney function (R4)",
        72,
        "M",
        "WARD",
        "Acute pyelonephritis",
        weight=60,
        creatinine=2.4,
        meds=[
            (
                "Inj Piperacillin-tazobactam 4.5 g IV q6h x 7 days",
                ("piperacillin/tazobactam", 4500.0, 4.0, "IV", 7),
            ),
            ("Inj Paracetamol 1 g IV TDS x 3 days", ("paracetamol", 1000.0, 3.0, "IV", 3)),
            ("Inj Pantoprazole 40 mg IV OD x 5 days", ("pantoprazole", 40.0, 1.0, "IV", 5)),
            ("Inj Ondansetron 4 mg IV TDS x 3 days", ("ondansetron", 4.0, 3.0, "IV", 3)),
        ],
        cultures=[urine(None, status="PENDING")],
        culture_lines=["Urine culture: sent before the first dose, report pending"],
    ),
    Case(
        "SYN-DEMO-07",
        "allergy",
        "Penicillin given to a patient with a penicillin allergy (R6)",
        31,
        "F",
        "OPD",
        "Cellulitis, non-purulent",
        weight=58,
        creatinine=0.7,
        allergy_status="KNOWN",
        allergies=["penicillin"],
        allergy_text="Penicillin (urticaria)",
        meds=[
            ("Cap Amoxicillin 500 mg PO TDS x 5 days", ("amoxicillin", 500.0, 3.0, "PO", 5)),
            ("Tab Ibuprofen 400 mg PO TDS x 3 days", ("ibuprofen", 400.0, 3.0, "PO", 3)),
        ],
    ),
    Case(
        "SYN-DEMO-08",
        "antibiotic_not_needed",
        "Antibiotic for a viral infection (R1)",
        24,
        "M",
        "OPD",
        "Viral URTI",
        weight=68,
        creatinine=0.9,
        meds=[
            ("Tab Azithromycin 500 mg PO OD x 3 days", ("azithromycin", 500.0, 1.0, "PO", 3)),
            PARA,
            ("Tab Cetirizine 10 mg PO OD x 5 days", ("cetirizine", 10.0, 1.0, "PO", 5)),
        ],
    ),
    Case(
        "SYN-DEMO-09",
        "inpatient_watch",
        "Inpatient pneumonia on the guideline regimen; both drugs are Watch tier, so R2 asks for "
        "a stewardship look",
        64,
        "F",
        "WARD",
        "Community-acquired pneumonia, inpatient ward",
        weight=58,
        creatinine=1.0,
        meds=[
            ("Inj Ceftriaxone 2 g IV OD x 5 days", ("ceftriaxone", 2000.0, 1.0, "IV", 5)),
            ("Tab Azithromycin 500 mg PO OD x 5 days", ("azithromycin", 500.0, 1.0, "PO", 5)),
            PARA,
            ("Inj Pantoprazole 40 mg IV OD x 5 days", ("pantoprazole", 40.0, 1.0, "IV", 5)),
        ],
    ),
    Case(
        "SYN-DEMO-10",
        "broad_spectrum_icu",
        "Carbapenem and vancomycin where the guideline gives ceftriaxone + azithromycin",
        69,
        "M",
        "ICU",
        "Community-acquired pneumonia, inpatient ICU",
        weight=72,
        creatinine=1.1,
        meds=[
            ("Inj Meropenem 1 g IV TDS x 7 days", ("meropenem", 1000.0, 3.0, "IV", 7)),
            ("Inj Vancomycin 1 g IV BD x 7 days", ("vancomycin", 1000.0, 2.0, "IV", 7)),
            ("Inj Pantoprazole 40 mg IV OD x 7 days", ("pantoprazole", 40.0, 1.0, "IV", 7)),
            ("Inj Paracetamol 1 g IV TDS x 3 days", ("paracetamol", 1000.0, 3.0, "IV", 3)),
        ],
    ),
    Case(
        "SYN-DEMO-11",
        "brand_low_dose",
        "Brand name read (Augmentin); daily dose below guideline (R3)",
        61,
        "M",
        "OPD",
        "Infective exacerbation of COPD",
        weight=66,
        creatinine=1.0,
        meds=[
            (
                "Tab Augmentin 625 mg PO BD x 5 days",
                ("amoxicillin/clavulanic acid", 625.0, 2.0, "PO", 5),
            ),
            ("Neb Salbutamol 2.5 mg QID x 5 days", ("salbutamol", 2.5, 4.0, None, 5)),
            ("Tab Prednisolone 40 mg PO OD x 5 days", ("prednisolone", 40.0, 1.0, "PO", 5)),
            ("Tab Montelukast 10 mg PO OD x 14 days", ("montelukast", 10.0, 1.0, "PO", 14)),
        ],
    ),
    Case(
        "SYN-DEMO-12",
        "de_escalation",
        "Culture back: step down from piperacillin-tazobactam to a narrower drug (C4)",
        45,
        "F",
        "WARD",
        "Acute pyelonephritis",
        weight=64,
        creatinine=0.8,
        meds=[
            (
                "Inj Piperacillin-tazobactam 4.5 g IV q6h x 7 days",
                ("piperacillin/tazobactam", 4500.0, 4.0, "IV", 7),
            ),
            ("Inj Paracetamol 1 g IV TDS x 3 days", ("paracetamol", 1000.0, 3.0, "IV", 3)),
        ],
        cultures=[
            urine(
                "Escherichia coli",
                **{
                    "Piperacillin-tazobactam": "S",
                    "Amikacin": "S",
                    "Ceftriaxone": "S",
                    "Ciprofloxacin": "R",
                },
            )
        ],
        culture_lines=[
            "Urine culture (final report): Escherichia coli",
            "Urine culture susceptibility: piperacillin-tazobactam (S), amikacin (S)",
            "Urine culture susceptibility: ceftriaxone (S), ciprofloxacin (R)",
        ],
    ),
    Case(
        "SYN-DEMO-13",
        "gastroenteritis",
        "Two antibiotics for gastroenteritis that needs none (R1)",
        27,
        "M",
        "OPD",
        "Acute gastroenteritis without danger signs",
        weight=70,
        creatinine=0.9,
        meds=[
            ("Tab Ciprofloxacin 500 mg PO BD x 5 days", ("ciprofloxacin", 500.0, 2.0, "PO", 5)),
            ("Tab Metronidazole 400 mg PO TDS x 5 days", ("metronidazole", 400.0, 3.0, "PO", 5)),
            (
                "Oral rehydration salts 200 ml PO after each loose stool",
                ("oral rehydration salts", None, None, "PO", None),
            ),
            ("Tab Ondansetron 4 mg PO TDS x 2 days", ("ondansetron", 4.0, 3.0, "PO", 2)),
        ],
    ),
    Case(
        "SYN-DEMO-14",
        "diabetic_foot",
        "Diabetic foot infection treated as the guideline says",
        56,
        "M",
        "OPD",
        "Diabetic foot infection, moderate",
        weight=78,
        creatinine=1.1,
        meds=[
            (
                "Tab Amoxicillin-clavulanate 625 mg PO TDS x 10 days",
                ("amoxicillin/clavulanic acid", 625.0, 3.0, "PO", 10),
            ),
            ("Tab Metformin 500 mg PO BD x 30 days", ("metformin", 500.0, 2.0, "PO", 30)),
            ("Tab Glimepiride 1 mg PO OD x 30 days", ("glimepiride", 1.0, 1.0, "PO", 30)),
            PARA,
        ],
        cultures=[{"specimen_type": "pus", "status": "PENDING", "isolates": []}],
        culture_lines=["Pus culture: deep tissue sample sent, report pending"],
    ),
    Case(
        "SYN-DEMO-15",
        "no_diagnosis",
        "No diagnosis written: the indication is undocumented",
        38,
        "F",
        "OPD",
        None,
        weight=60,
        creatinine=0.8,
        meds=[
            ("Tab Azithromycin 500 mg PO OD x 3 days", ("azithromycin", 500.0, 1.0, "PO", 3)),
            PARA,
            ("Tab Levocetirizine 5 mg PO OD x 5 days", ("levocetirizine", 5.0, 1.0, "PO", 5)),
        ],
    ),
    Case(
        "SYN-DEMO-16",
        "uncertain_diagnosis",
        "Uncertain diagnosis ('UTI?'): not mapped, the reviewer must choose",
        50,
        "F",
        "OPD",
        "UTI?",
        weight=66,
        creatinine=0.9,
        meds=[("Tab Cefixime 200 mg PO BD x 7 days", ("cefixime", 200.0, 2.0, "PO", 7))],
    ),
    Case(
        "SYN-DEMO-17",
        "nitrofurantoin_renal",
        "Nitrofurantoin in an older patient with poor kidney function (R4)",
        78,
        "F",
        "OPD",
        "Uncomplicated cystitis",
        weight=50,
        creatinine=1.6,
        meds=[
            ("Tab Nitrofurantoin 100 mg PO BD x 5 days", ("nitrofurantoin", 100.0, 2.0, "PO", 5)),
            ("Tab Amlodipine 5 mg PO OD x 30 days", ("amlodipine", 5.0, 1.0, "PO", 30)),
            ("Tab Atorvastatin 10 mg PO OD x 30 days", ("atorvastatin", 10.0, 1.0, "PO", 30)),
        ],
        cultures=[urine(None, status="PENDING")],
        culture_lines=["Urine culture: sent, report pending"],
    ),
    Case(
        "SYN-DEMO-18",
        "paediatric",
        "Child: adult dose rules do not apply, so the dose is not judged",
        8,
        "M",
        "OPD",
        "Acute pharyngitis, Centor score 3 or more",
        weight=24,
        creatinine=0.4,
        meds=[
            ("Cap Amoxicillin 250 mg PO TDS x 7 days", ("amoxicillin", 250.0, 3.0, "PO", 7)),
            ("Tab Paracetamol 250 mg PO TDS x 3 days", ("paracetamol", 250.0, 3.0, "PO", 3)),
        ],
    ),
]


def run_engine(cases: list[Case]) -> dict[str, dict]:
    from fastapi.testclient import TestClient

    from backend.stewardship.api import create_app
    from backend.stewardship.audit import JsonlAuditLog
    from backend.stewardship.drugs import Catalog
    from backend.stewardship.renal import RenalDosing
    from backend.stewardship.rulepack import YamlRulePack
    from backend.stewardship.service import StewardshipService

    with tempfile.TemporaryDirectory() as tmp:
        service = StewardshipService(
            catalog=Catalog.load(),
            rulepack=YamlRulePack(),
            renal=RenalDosing.load(),
            audit=JsonlAuditLog(Path(tmp) / "audit.jsonl"),
        )
        client = TestClient(create_app(service))
        out = {}
        for case in cases:
            response = client.post("/api/evaluate", json=case.request())
            response.raise_for_status()
            report = response.json()
            drugs = {o["id"]: o["generic"] for o in report["orders"]}
            out[case.id] = {
                "status": report["status"],
                "syndrome": report["syndrome"]["code"],
                "findings": [
                    {
                        "rule": i["rule_id"],
                        "drug": drugs.get(i["order_id"]),
                        "outcome": i["outcome"],
                        "message": i["message"],
                    }
                    for i in report["items"]
                    if i["outcome"] != "PASS"
                ],
            }
        return out


def main() -> None:
    expected = run_engine(CASES)
    cases = {
        "_label": LABEL + " Not used by the engine or the tests.",
        "_format": "request: the exact body of POST /api/episodes. prescription_text: what to "
        "paste as the typed prescription. expected: the non-PASS findings the engine returned when "
        "build_cases.py was run; every other check passed.",
        "cases": [
            {
                "case_id": c.id,
                "demonstrates": c.demonstrates,
                "prescription_text": c.prescription_text,
                "request": c.request(),
                "expected": expected[c.id],
            }
            for c in CASES
        ],
    }
    prescriptions = {
        "_label": LABEL + " Exact text printed on each demo prescription image.",
        "_format": "rows: printed top to bottom. A row is [style, text] or [style, left column, "
        "right column]. expected_orders: the DrugOrder fields read_orders must produce from the "
        "whole page text. case_id links to cases.json.",
        "page": PAGE,
        "cases": [
            {
                "case_id": c.id,
                "image": f"images/{c.id}_{c.slug}.png",
                "rows": c.rows(),
                "expected_orders": c.expected_orders(),
            }
            for c in CASES
        ],
    }
    patients = {
        "_label": LABEL + " Stand-in for the hospital record system: GET /api/patients/{id} "
        "reads it to pre-fill the review form.",
        "records": [{"patient": c.patient, "cultures": c.cultures} for c in CASES],
    }
    for name, data in (
        ("cases.json", cases),
        ("prescriptions.json", prescriptions),
        ("patients.json", patients),
    ):
        (HERE / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print("wrote", name)
    for c in cases["cases"]:
        e = c["expected"]
        flags = "; ".join(f"{f['rule']} {f['drug'] or ''} {f['outcome']}" for f in e["findings"])
        print(f"{c['case_id']} {e['status']:8} {e['syndrome']} | {flags or 'all PASS'}")


if __name__ == "__main__":
    main()
