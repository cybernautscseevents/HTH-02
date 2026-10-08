# Kshema — Project State

Last updated: 2026-09-14 (consolidation pass + GPU migration — see
`results/FINAL_BENCHMARK_REPORT.md` for full numbers; this file tracks status and
open work only).

## Decided / Done

- **M1 (OCR engine selection): DECIDED — GLM-OCR.** Best accuracy on the final
  1,018-image clean set (CER 0.332, exact-match 32.4%), ahead of TrOCR-large, PaddleOCR,
  and docTR+PARSeq. See `results/FINAL_BENCHMARK_REPORT.md` §2, §6.
- **M3 (OCR normalization / error-recovery module): BUILT and PATCHED.**
  `backend/modules/module3/ocr_normalization.py` implements the full 5-stage pipeline
  (candidate generation → composite scoring → context validation → decide →
  brand→generic lookup) plus all safety rules, including the different-generic LASA
  collision safeguard (Rule 5, e.g. Apeclo/Apeelo). 3/3 unit tests passing
  (`backend/modules/module3/test_ocr_normalization.py`). Zero WRONG (confident-wrong-drug)
  outcomes on the clean set at both calibrated thresholds (PaddleOCR 0.72, GLM-OCR 0.82).
  See `results/FINAL_BENCHMARK_REPORT.md` §3.
- **Dataset audit: COMPLETE.** Canonical clean set is `results/RxHandBD_Test_Label_clean.csv`
  (1,018 images), built from `results/rxhandbd_known_bad_rows.csv` (97 confirmed-bad rows:
  74 cluster-shift + 23 isolated-typo) via `scripts/build_clean_test_set.py`. All three
  benchmark scripts default to it; `--use-raw` correctly falls back to the original
  1,115-row `Test_Label.csv`. See `results/FINAL_BENCHMARK_REPORT.md` §1, §5.
- **GLM-OCR latency: RESOLVED via GPU migration.** Inference moved from CPU to the
  local RTX 3050 (bf16, `device_map="cuda:0"`) in `benchmarks/new_models_benchmark.py`
  and `benchmarks/glm_batch_benchmark.py`, with a clean CPU fallback if GPU load fails.
  Measured ~0.31s/image at batch size 8 (vs ~5.8–10s/image on CPU, a ~16–19x speedup).
  GPU output confirmed identical to CPU (10/10 exact match on smoke-test images).
  Peak VRAM 2.6GB, comfortably within the 3050's 4GB. A realistic 3–8-crop
  prescription now completes in <2.5s — within a synchronous UX budget. See
  `results/FINAL_BENCHMARK_REPORT.md` §4.

## Open / Next

1. **Pipeline integration** — wire GLM-OCR (now GPU-accelerated) into the orchestrator
   as the M1 OCR engine (currently only exercised via standalone benchmark scripts,
   not `run_rxguard.py`).
2. **Full-prescription-level dataset still needed.** RxHandBD is isolated single-word
   crops only; M3's Stage 3 context validation (dosage/formulation signal) has no real
   data to exercise it yet. A full-prescription-line dataset is needed to test
   normalization with real line-level context, not just isolated tokens.
3. **PaddleOCR mobile_rec is unverified.** A previously-reported mobile_rec comparison
   point exists only as a hardcoded literal in `new_models_benchmark.py`, with no
   per-image data to confirm it against the current clean 1,018-row set. Re-run and log
   it properly if a mobile_rec comparison is needed going forward.
4. **CPU fallback path is untested end-to-end** — the new `_load_glm()` GPU→CPU
   fallback logic is implemented but only the GPU path has been exercised on this
   machine (which always has CUDA available). If a deployment target may lack a GPU,
   verify the fallback actually engages correctly there.

## Out of scope for this tracker (see other modules)

- Drug-drug interaction (DDI), dose adjustment, pregnancy safety modules — not touched,
  not tracked here per explicit instruction.
