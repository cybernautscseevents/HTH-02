---
name: karpathy-guidelines
description: Coding guidelines for the Hackatopia HC-03 Antibiotic Stewardship build. Use when writing, reviewing, or refactoring code in this repo to keep it simple, tested, surgical, and safe for clinical decision support.
license: MIT
---

# Coding Guidelines (HC-03 hackathon edition)

Adapted from forrestchang/andrej-karpathy-skills (MIT) for a 24-hour, three-person build
of a deterministic antibiotic stewardship engine. Judges read the code.

## 1. Think before coding, but don't stall

- State assumptions in one line before non-trivial changes.
- If the spec or existing code already answers a question, follow it and move on. Do not ask.
- Ask only when the ambiguity is **clinical or safety-relevant** (a dose range, a guideline
  choice, what counts as "missing" data). Never guess clinical content.
- If a simpler approach exists, say so and use it.

## 2. Simplicity first

- Minimum code that solves the task. No speculative features, plugin systems, or config
  nobody asked for.
- No abstraction for a single use. Plain functions over classes unless state is real.
- If 200 lines could be 50, rewrite it.
- Do not add error handling for impossible cases. Missing or unparseable **clinical input is
  not impossible**: it must produce a `CANNOT_ASSESS` finding, never a silent pass.

## 3. Surgical changes

- Touch only files your task owns. Teammates own other modules; shared models
  (`schemas.py`, `ports.py`) change only through the core lead.
- Match the surrounding style. Don't reformat or "improve" unrelated code.
- Remove imports and helpers that your own change made unused. Mention other dead code, don't
  delete it.

## 4. Goal-driven execution

- Turn every task into a test first: "add rule R3" → write the PASS / FLAG / CANNOT_ASSESS
  tests, then make them pass.
- For multi-step work, state a short plan with a check per step:
  `1. [step] → verify: [test or command]`
- Done means `pytest` and `ruff check` pass, not "looks right".

## 5. Non-negotiables for this project

- **No LLM, network, or database calls in decision code** (rules, culture checks, coverage,
  episode evaluation). Inputs in, findings out. Pure, deterministic functions.
- Every check returns `PASS`, `FLAG`, or `CANNOT_ASSESS`, with a stable `rule_id`.
- Every guideline-derived finding and every data row carries its source and page.
  Never invent a guideline, dose, duration, or resistance number. If a value isn't in a
  cited source, leave it out and say so.
- Synthetic data is always labelled synthetic.
- The system suggests; a pharmacist decides. Never auto-stop or auto-switch a drug.

## 6. Code standards

- Type hints everywhere; Pydantic v2 models for data crossing module boundaries.
- Module docstring says why the module exists; public functions have short docstrings.
- `logging.getLogger(__name__)`, never `print`. No bare `except`, no `except Exception: pass`.
- No hard-coded paths or thresholds outside `config.py`.
- Plain clinical English in messages; generic drug names in lower case; no emojis.
- Small commits with clear messages. No AI attribution lines in commits or PRs.
