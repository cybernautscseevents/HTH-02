# Application flow: prescription to action

```text
typed prescription / PDF text / frontend form
  -> intake.py        Catalog.normalize -> DrugOrder[]; syndrome code; cultures -> Specimen[]
  -> Episode
  -> evaluate_episode()   R0-R6 + C1,C3-C9, real YamlRulePack (NCDC 2025), Catalog, RenalDosing
  -> Evaluation           unchanged engine output (source of truth)
  -> service.py           adds, per finding: action (advice.py), guideline passages + explanation (evidence.py)
  -> api.py               HTTP, no clinical logic
  -> frontend             Prescription -> Audit -> Action
  -> POST /api/reviews    apply_review() -> JsonlAuditLog (runtime/audit.jsonl)
```

Run: `uvicorn backend.main:app --port 8000`, then in `frontend/` copy `.env.example` to
`.env.local` and `npm run dev`. Install: `pip install -r requirements-api.txt`.

## API (`backend/stewardship/api.py`)

| Endpoint | Purpose |
|---|---|
| `GET /api/syndromes` | The 13 accepted syndrome codes with their NCDC section and page |
| `POST /api/parse-prescription` | Preview how typed text becomes orders (unknown drugs stay unaccepted) |
| `POST /api/evaluate` | One call: request -> `EvaluationReport` |
| `POST /api/episodes`, `POST /api/episodes/{id}/evaluate`, `GET /api/evaluations/{id}` | Same flow in two steps (the frontend uses these) |
| `POST /api/reviews`, `GET /api/audit`, `GET /api/timeout-due` | Review -> audit log; time-out list |

`EvaluationReport` is the engine's `Evaluation` plus `items` (each finding with `action`,
`explanation`, `guideline_passages`), `culture`, `syndrome`, `orders` and `warnings`.

Request body: `patient`, `setting`, `syndrome_code` (or `diagnosis_text`), `prescription` (one
medicine per line; an optional "Prescription:" marker skips header lines), `cultures`.

## Syndrome

An explicit `syndrome_code` must be one of the rule-pack codes (else 422). Free text is mapped
only through the phrase table in `intake.DIAGNOSIS_PHRASES`, and only when it names exactly one
syndrome. "Pneumonia" or "cellulitis" alone are not mapped, because the rule pack splits them by
setting/severity. Unresolved means no syndrome: R1, R3 and R5 return CANNOT_ASSESS and the report
carries a warning. No model chooses the syndrome.

## Cultures

| Input | Engine state | Meaning |
|---|---|---|
| none, or `NOT_SENT` | no specimen | Unknown. Not negative, not susceptible. Summary says "Culture result unavailable"; C1 may flag |
| `PENDING` | pending | Result not in yet |
| `NO_GROWTH` | negative | C5 may flag after 48 h; the clinician decides |
| `GROWTH_NO_AST` | growth, no susceptibilities | Waiting for the panel |
| `FINAL` + isolate(s) | positive | C3 (resistant or intrinsically resistant), C4, C7, C8, C9 run |

`FINAL` with no isolate, isolates on a `NO_GROWTH` culture, or a susceptibility agent the catalog
does not recognise are rejected (422), not repaired. Organisms are looked up in Person 2's
reference list; unknown ones raise C9 and intrinsic resistance is reported as not checked.

## Actions

`advice.py` maps each (rule, outcome) to fixed text, e.g. R3 FLAG -> "Review dose before
administration against the guideline range." A drug name appears in an action only when the
rule's own suggestion carries one (a guideline regimen). A pass has no action.

## Evidence retrieval (ChromaDB)

`evidence.py` indexes the rule-pack rows (document, section, page, syndrome) in ChromaDB; for each
non-pass finding it retrieves the passages of the episode's syndrome and the explainer words the
result with its source. `scripts/ingest_guidelines.py <pdf> --document <title>` adds a whole PDF
by numbered section (labelled `pdf p. N`, which can differ from the printed page); set
`HC03_CHROMA_DIR` or use `runtime/chroma` and the API loads it. Retrieval never changes an
outcome or severity.

- Default embedding is a deterministic hashed bag-of-words, so it works offline and is
  reproducible; it matches words, not meaning. Swap in a sentence-embedding function for fuzzier
  retrieval.
- `TemplateExplainer` is the default. `LlmExplainer(complete)` accepts any text-in/text-out
  callable and is told to explain, not judge; it is not wired to a provider. Any failure falls
  back to the template.
- LangChain is not used; it would add dependencies for what is one Chroma query.

## Limits

- State is in memory (episodes, evaluations); only the audit log is persisted.
- Typed lines need a form or route ("Tab", "PO", "IV") or R3/R5 cannot run; combination strengths
  ("500/125") are not read as a dose.
- Non-antibiotic lines (e.g. paracetamol) come back as unrecognised by R0 because the lexicon
  covers antibiotics.
- PDF text is a separate step upstream; this service takes text.
