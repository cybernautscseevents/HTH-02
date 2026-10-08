"""Engine thresholds and data locations, in one place so no other module hard-codes them.

Every value can be overridden with an environment variable for deployment or testing.
"""

import os
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = _PACKAGE_DIR.parents[1]

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

# Hours after the first antibiotic dose when the antibiotic time-out becomes due.
TIMEOUT_HOURS = float(os.getenv("HC03_TIMEOUT_HOURS", "48"))

# A daily dose above (guideline maximum x this factor) is escalated from MODERATE to HIGH.
HIGH_DOSE_FACTOR = float(os.getenv("HC03_HIGH_DOSE_FACTOR", "1.5"))

# Dose rules are written for adults; younger patients get CANNOT_ASSESS.
ADULT_AGE_YEARS = int(os.getenv("HC03_ADULT_AGE_YEARS", "18"))

# Where the application keeps its append-only audit log and the optional persisted guideline
# index built by scripts/ingest_guidelines.py.
RUNTIME_DIR = Path(os.getenv("HC03_RUNTIME_DIR", str(REPO_ROOT / "runtime")))
AUDIT_LOG_PATH = RUNTIME_DIR / "audit.jsonl"
CHROMA_DIR = Path(os.getenv("HC03_CHROMA_DIR", str(RUNTIME_DIR / "chroma")))

# Optional language-model summary of an evaluation (summary.py). Explanation only; it never
# changes a result. Off unless configured: HC03_LLM_PROVIDER=groq|gemini with HC03_LLM_API_KEY
# (base URL and model have defaults), or HC03_LLM_BASE_URL and HC03_LLM_MODEL for any other
# OpenAI-compatible API (e.g. http://localhost:11434/v1 for Ollama). Set the key in the
# environment only, never in a file in the repository.
LLM_PROVIDER = os.getenv("HC03_LLM_PROVIDER") or None
LLM_BASE_URL = os.getenv("HC03_LLM_BASE_URL") or None
LLM_MODEL = os.getenv("HC03_LLM_MODEL") or None
LLM_API_KEY = os.getenv("HC03_LLM_API_KEY") or None
LLM_TIMEOUT_S = float(os.getenv("HC03_LLM_TIMEOUT_S", "20"))
