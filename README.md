# HC-03 Antibiotic Stewardship Copilot

Checks an antibiotic prescription against the Indian national treatment guideline (NCDC 2025),
the patient's kidney function, allergies and culture results, and tells the pharmacist what to
do. Every check is deterministic and cites its source; anything it cannot check is reported as
`CANNOT_ASSESS`, never as a pass. No model makes a clinical decision.

## One pipeline

```
prescription image ──► prescription_ocr (GLM-OCR or Qwen-VL) ──► transcript ┐
typed prescription ─────────────────────────────────────────────────────────┤
                                                                            ▼
                        prescription_ocr/transcript.py + orders.py   (line parser)
                                                                            ▼
                        backend/stewardship/drugs.py  Catalog.normalize  (drug identity)
                                                                            ▼
                        DrugOrder[]  ──►  Episode   (backend/stewardship/intake.py)
                                                                            ▼
                        evaluate_episode()          (backend/stewardship/episode.py)
                          R0 identified · R1 indication · R2 AWaRe · R3 dose · R4 renal
                          R5 duration · R6 allergy   (rules.py, renal.py)
                          C1, C3-C9 culture rules    (culture.py)
                                                                            ▼
                        Evaluation ──► action + explanation (service.py, advice.py)
                                                                            ▼
                        FastAPI (api.py, backend/main.py) ──► frontend (Next.js)
```

| Part | Where |
|---|---|
| Stewardship engine, rules, culture, review, audit, time-out | `backend/stewardship/` |
| Guideline rule pack (13 hand-checked + 93 imported NCDC syndromes) | `backend/stewardship/rulepack/`, `docs/RULEPACK.md` |
| Drug catalog, AWaRe, brands, renal dosing data | `data/`, `docs/SOURCES.md` |
| Prescription OCR (image → orders) | `prescription_ocr/` |
| API | `backend/stewardship/api.py`, entry point `backend/main.py` |
| Frontend | `frontend/` |
| Tests | `backend/tests/` |
| Superseded RxGuard pipeline (not used) | `legacy/` |

## Run

Backend (Python 3.11+):

```
pip install -r requirements-api.txt
uvicorn backend.main:app --port 8000          # http://localhost:8000/api/health
```

Frontend (Node 20+):

```
cd frontend && npm install
cp .env.example .env.local                     # NEXT_PUBLIC_USE_MOCK=false → real backend
npm run dev                                    # http://localhost:3000
```

Without `.env.local` the frontend runs on built-in mock data (`NEXT_PUBLIC_USE_MOCK` unset).

AI-worded summary (optional). The evaluation summary is rule-based unless a language model is
configured; the model only rewords the rule results, its text is checked, and any failure falls
back to the rule-based summary. Set these in the backend's environment (never in a committed file):

| Variable | Meaning |
|---|---|
| `HC03_LLM_PROVIDER` | `groq` or `gemini` (fills in the base URL and a default model) |
| `HC03_LLM_API_KEY` | the provider's API key; a hosted provider without a key stays off |
| `HC03_LLM_API_KEYS` | optional comma-separated extra keys; requests take keys in turn, and a key that hits the rate limit (HTTP 429) rests for the provider's Retry-After while the others carry on |
| `HC03_LLM_MODEL` | optional model override (default for `groq`: `qwen/qwen3.8-27b`) |
| `HC03_LLM_BASE_URL` | optional; any other OpenAI-compatible endpoint, e.g. a local Ollama |
| `HC03_LLM_TIMEOUT_S` | request timeout in seconds (default 20) |
| `HC03_CHAT_MAX_QUESTIONS` | model calls allowed per evaluation for "Ask about this result" (default 20; repeated questions are cached and free) |

OCR (optional, needs a GPU-capable `torch`; not needed for the engine or the typed demo):

```
pip install -r requirements-ocr.txt
python -m prescription_ocr IMAGE [--engine glm|qwen]
```

Tests and lint:

```
python -m pytest                               # backend + OCR parsing tests (no model download)
ruff check . && ruff format --check .
cd frontend && npx tsc --noEmit && npm run build
```

More: `docs/APPLICATION.md` (API and flow), `docs/CORE_SPEC.md` (engine design),
`docs/RULEPACK.md`, `docs/SOURCES.md`, `docs/OCR_REAL_PRESCRIPTION_TEST.md`.
