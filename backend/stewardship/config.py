"""Engine thresholds and data locations, in one place so no other module hard-codes them.

Every value can be overridden with an environment variable for deployment or testing.
"""

import os
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = _PACKAGE_DIR.parents[1]

DATA_DIR = Path(os.getenv("HC03_DATA_DIR", str(REPO_ROOT / "data")))
RULEPACK_DIR = Path(os.getenv("HC03_RULEPACK_DIR", str(_PACKAGE_DIR / "rulepack")))

AWARE_CSV = DATA_DIR / "aware.csv"
LEXICON_CSV = DATA_DIR / "indian_drug_lexicon.csv"
INTRINSIC_RESISTANCE_CSV = DATA_DIR / "intrinsic_resistance.csv"
RENAL_DOSING_CSV = DATA_DIR / "renal_dosing.csv"

# Similarity (0-1) above which a misspelt drug name is offered as a candidate. Candidates are
# never accepted automatically; a person confirms them.
FUZZY_CUTOFF = float(os.getenv("HC03_FUZZY_CUTOFF", "0.8"))

# Hours after the first antibiotic dose when the antibiotic time-out becomes due.
TIMEOUT_HOURS = float(os.getenv("HC03_TIMEOUT_HOURS", "48"))

# A daily dose above (guideline maximum x this factor) is escalated from MODERATE to HIGH.
HIGH_DOSE_FACTOR = float(os.getenv("HC03_HIGH_DOSE_FACTOR", "1.5"))

# Dose rules are written for adults; younger patients get CANNOT_ASSESS.
ADULT_AGE_YEARS = int(os.getenv("HC03_ADULT_AGE_YEARS", "18"))
