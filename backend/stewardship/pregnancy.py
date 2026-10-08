"""Antibiotics to avoid in pregnancy, read once from data/pregnancy_caution.csv (rule R7).

Each row names one drug, why it is avoided, and the source. A drug not in the table has no
pregnancy caution recorded here; that is not a statement that it is safe in pregnancy.
"""

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from . import config
from .schemas import Evidence


@dataclass(frozen=True)
class PregnancyCaution:
    generic: str
    reason: str
    evidence: Evidence


def load_pregnancy_cautions(
    path: Path = config.PREGNANCY_CAUTION_CSV,
) -> dict[str, PregnancyCaution]:
    with path.open(encoding="utf-8") as f:
        return {
            row["generic"]: PregnancyCaution(
                generic=row["generic"],
                reason=row["reason"],
                evidence=Evidence(
                    source_id=row["source_id"], title=row["title"], page=row["section"]
                ),
            )
            for row in csv.DictReader(f)
        }


@cache
def pregnancy_cautions() -> dict[str, PregnancyCaution]:
    return load_pregnancy_cautions()
