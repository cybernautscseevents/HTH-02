"""Engine thresholds and data locations, in one place so no other module hard-codes them.

Every value can be overridden with an environment variable for deployment or testing.
"""

import os
import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = _PACKAGE_DIR.parents[1]


def _load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from the repo-root .env (gitignored) into the environment.

    Variables already set in the environment win. Skipped under pytest so a developer's local
    keys never switch on a provider during tests."""
    if "pytest" in sys.modules or not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(REPO_ROOT / ".env")

DATA_DIR = Path(os.getenv("HC03_DATA_DIR", str(REPO_ROOT / "data")))
RULEPACK_DIR = Path(os.getenv("HC03_RULEPACK_DIR", str(_PACKAGE_DIR / "rulepack")))
SYNDROMES_YAML = RULEPACK_DIR / "syndromes.yaml"
# Syndromes converted from the NCDC dataset by scripts/import_ncdc.py (generated, not edited).
NCDC_SYNDROMES_YAML = RULEPACK_DIR / "syndromes_ncdc.yaml"
NCDC_MANIFEST_YAML = RULEPACK_DIR / "ncdc_import.yaml"
NCDC_DATASET_YAML = DATA_DIR / "reference" / "ncdc" / "syndromes_ncdc_2025.yaml"
# ICMR AMRSN 2023 surveillance susceptibility table; advisory context only, never a rule input.
SURVEILLANCE_CSV = DATA_DIR / "reference" / "ncdc" / "antibiogram_icmr_amrsn_2023.csv"

AWARE_CSV = DATA_DIR / "aware.csv"
DRUG_ALIASES_CSV = DATA_DIR / "drug_aliases.csv"
BRANDS_CSV = DATA_DIR / "brands_india.csv"
INTRINSIC_RESISTANCE_CSV = DATA_DIR / "intrinsic_resistance.csv"
PREGNANCY_CAUTION_CSV = DATA_DIR / "pregnancy_caution.csv"
DRUG_DISEASE_CSV = DATA_DIR / "drug_disease.csv"
DRUG_DISEASE_LABELS_CSV = DATA_DIR / "drug_disease_labels.csv"
ORGANISMS_TXT = DATA_DIR / "reference" / "amrie" / "Organisms.txt"
RENAL_DOSING_CSV = DATA_DIR / "renal_dosing.csv"
# Common non-antibiotic drugs (WHO ATC codes), identified so they are not left unresolved.
NON_ANTIBIOTICS_CSV = DATA_DIR / "non_antibiotics.csv"
# Patient records the review form can be pre-filled from (records.py). Synthetic in the demo.
PATIENT_RECORDS_JSON = Path(
    os.getenv("HC03_PATIENT_RECORDS_JSON", str(DATA_DIR / "demo_synthetic" / "patients.json"))
)

# Similarity (0-1) above which a misspelt drug name is offered as a candidate. Candidates are
# never accepted automatically; a person confirms them.
FUZZY_CUTOFF = float(os.getenv("HC03_FUZZY_CUTOFF", "0.8"))

# A surveillance susceptibility from fewer isolates than this is marked as limited evidence
# (NCDC antibiogram guidance, "Influence of Small Numbers of Isolates", as cited by the dataset
# schema on branch complete-verification-incomplete).
SURVEILLANCE_MIN_ISOLATES = int(os.getenv("HC03_SURVEILLANCE_MIN_ISOLATES", "30"))

# Time after the first antibiotic dose when reassessment becomes due. Minutes take precedence so
# demos can use a short interval without changing the clinical 48-hour default.
_timeout_minutes = os.getenv("HC03_TIMEOUT_MINUTES")
TIMEOUT_HOURS = (
    float(_timeout_minutes) / 60
    if _timeout_minutes
    else float(os.getenv("HC03_TIMEOUT_HOURS", "48"))
)

# A daily dose above (guideline maximum x this factor) is escalated from MODERATE to HIGH.
HIGH_DOSE_FACTOR = float(os.getenv("HC03_HIGH_DOSE_FACTOR", "1.5"))

# Dose rules are written for adults; younger patients get CANNOT_ASSESS.
ADULT_AGE_YEARS = int(os.getenv("HC03_ADULT_AGE_YEARS", "18"))

# Age range in which an unrecorded pregnancy status blocks a pregnancy-caution drug (R7).
CHILDBEARING_AGE_MIN = int(os.getenv("HC03_CHILDBEARING_AGE_MIN", "12"))
CHILDBEARING_AGE_MAX = int(os.getenv("HC03_CHILDBEARING_AGE_MAX", "50"))

# Where the application keeps its append-only audit log and the optional persisted guideline
# index built by scripts/ingest_guidelines.py.
RUNTIME_DIR = Path(os.getenv("HC03_RUNTIME_DIR", str(REPO_ROOT / "runtime")))
AUDIT_LOG_PATH = RUNTIME_DIR / "audit.jsonl"
CHROMA_DIR = Path(os.getenv("HC03_CHROMA_DIR", str(RUNTIME_DIR / "chroma")))

# Optional language-model summary of an evaluation (summary.py). Explanation only; it never
# changes a result. Off unless configured: HC03_LLM_PROVIDER=groq|gemini with one key in
# HC03_LLM_API_KEY or a comma-separated rotation in HC03_LLM_API_KEYS (base URL and model have
# defaults), or HC03_LLM_BASE_URL and HC03_LLM_MODEL for any other OpenAI-compatible API.
LLM_PROVIDER = os.getenv("HC03_LLM_PROVIDER") or None
LLM_BASE_URL = os.getenv("HC03_LLM_BASE_URL") or None
LLM_MODEL = os.getenv("HC03_LLM_MODEL") or None
LLM_API_KEY = os.getenv("HC03_LLM_API_KEY") or None
LLM_API_KEYS = tuple(
    dict.fromkeys(
        key.strip()
        for key in (LLM_API_KEY, *(os.getenv("HC03_LLM_API_KEYS") or "").split(","))
        if key and key.strip()
    )
)
LLM_TIMEOUT_S = float(os.getenv("HC03_LLM_TIMEOUT_S", "20"))


# Drug-drug interaction source: the local DrugBank XML export (licensed, never committed)
# and the pair index built from it once into the gitignored runtime directory.
def _resolve_drugbank_xml() -> Path:
    env = os.getenv("HC03_DRUGBANK_XML_PATH") or os.getenv("DRUGBANK_XML_PATH")
    if env:
        return Path(env)
    for name in ("drugbank.xml", "drugbank_full_database.xml"):
        p = REPO_ROOT / name
        if p.exists():
            return p
    return REPO_ROOT / "drugbank.xml"


DRUGBANK_XML_PATH = _resolve_drugbank_xml()
DDI_INDEX_PATH = Path(
    os.getenv(
        "HC03_DDI_INDEX_PATH",
        os.getenv("DDI_INDEX_PATH", str(RUNTIME_DIR / "drugbank_ddi_index.sqlite")),
    )
)
