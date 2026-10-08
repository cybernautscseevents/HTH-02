# Legacy: RxGuard pipeline (superseded, not part of the application)

`rxguard/` is the project's earlier prescription-audit pipeline (March-October 2026, modules 1-9),
moved here unchanged with `git mv` so its history is kept. It is **not** imported by the
application, its tests are not part of `pytest`, and it is not linted with the application code.

It was isolated because it is a second, competing implementation of what the application now does
in one place:

| RxGuard (here) | Replaced by (canonical) |
|---|---|
| `backend/orchestrator.py`, `run_rxguard.py` (CLI pipeline) | `backend/stewardship/service.py`, `api.py`, `backend/main.py` |
| module1 Qwen/TrOCR, `backend/script.py` PaddleOCR | `prescription_ocr/` (GLM-OCR, Qwen-VL) |
| module2 Med7 NER, module3 drug/OCR normalization | `prescription_ocr/transcript.py`, `orders.py`, `backend/stewardship/drugs.py` |
| module5 LLM appropriateness, module6 RAG stewardship | `backend/stewardship/rules.py` (R0-R6), `culture.py`, rule pack |
| module7 dose adjustment | `backend/stewardship/renal.py` (R4) |
| `report_generator.py` (PDF report) | API evaluation report + frontend |

Not yet replaced, kept here for later: module4 diagnosis validation, module8 drug-drug
interactions, module9 pregnancy safety. They depend on LLMs, LangChain, spaCy and data paths
outside the repo (module9 points at `/home/kart/Desktop/Kshema/...`).

The layout under `rxguard/` mirrors the old repository root, so relative paths still resolve:

```
cd legacy/rxguard
pip install -r requirements.txt          # heavy: torch, paddleocr, spacy, langchain, ...
python run_rxguard.py --image path/to/prescription.jpg --output report.pdf
python -m pytest backend/modules          # module3 needs rapidfuzz
```

Also here: `benchmarks/` and `scripts/build_clean_test_set.py` (the OCR model selection study
that chose GLM-OCR; results are summarised in `task.md`), and the data only these modules read
(`data/fda_label_database.json`, `data/fda_pllr_database.json`, `data/indian_drug_lexicon.csv`).
