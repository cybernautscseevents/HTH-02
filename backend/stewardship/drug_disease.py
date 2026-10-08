"""Label cautions for antibiotics in patients with a given condition, read once from
data/drug_disease.csv and data/drug_disease_labels.csv (rule R8).

Each row is the first sentence of a US FDA label section that names the condition, quoted as
written. A drug or condition not in the table has no caution recorded here; that is not a
statement that the drug is safe in that condition.
"""

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from . import config
from .schemas import Comorbidity, Evidence

CONTRAINDICATION = "contraindication"


@dataclass(frozen=True)
class DrugDiseaseCaution:
    generic: str
    condition: Comorbidity
    kind: str  # "contraindication" (Contraindications, Boxed Warning) or "warning"
    evidence: Evidence


def load_drug_disease_cautions(
    path: Path = config.DRUG_DISEASE_CSV, labels_path: Path = config.DRUG_DISEASE_LABELS_CSV
) -> dict[str, tuple[DrugDiseaseCaution, ...]]:
    with labels_path.open(encoding="utf-8") as f:
        labels = {row["generic"]: row for row in csv.DictReader(f)}
    cautions: dict[str, list[DrugDiseaseCaution]] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            label = labels[row["generic"]]
            cautions.setdefault(row["generic"], []).append(
                DrugDiseaseCaution(
                    generic=row["generic"],
                    condition=Comorbidity(row["condition"]),
                    kind=row["kind"],
                    evidence=Evidence(
                        source_id=f"fda-label-{label['set_id']}",
                        title=label["title"],
                        page=row["section"],
                        quote=row["quote"],
                    ),
                )
            )
    return {generic: tuple(rows) for generic, rows in cautions.items()}


@cache
def drug_disease_cautions() -> dict[str, tuple[DrugDiseaseCaution, ...]]:
    return load_drug_disease_cautions()
