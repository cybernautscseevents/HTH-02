---
name: deslop
description: Remove AI-generated code slop from the current branch before merging, without removing the project's deliberate safety checks. Use when cleaning up a branch, before opening a PR, or when asked to deslop or polish code for judges.
---

# Remove AI Code Slop (HC-03 edition)

Adapted from davila7/claude-code-templates (MIT), `skills/sentry/deslop`.
Clean the code this branch introduced so it reads like a careful human wrote it.

## Process

1. Find the base branch: `git rev-parse --verify main` (fall back to `master`).
2. Get the diff: `git diff main...HEAD` (plus `git diff` for uncommitted work).
3. Review only lines this branch added or changed. Leave pre-existing code alone.
4. Remove slop, keeping every legitimate change and every protected pattern below.
5. Verify: `ruff check .` and `pytest -q` must pass after cleanup. If they fail, fix or revert
   the cleanup that broke them.
6. Report a 1–3 sentence summary of what changed.

## Remove

- Comments that restate the code, narrate the change ("now we...", "updated to..."), or
  don't match the comment style of the rest of the file.
- Defensive checks and `try/except` blocks around trusted, already-validated code paths.
- `except Exception: pass`, bare `except`, and exceptions swallowed without logging.
- Inline imports in Python (move to the top of the file); unused imports and variables.
- `print` statements (use `logging`), leftover debug code, commented-out code.
- `Any` / `# type: ignore` used to dodge a type problem that can be fixed properly.
- Emojis and decorative banners in code, comments, log messages, and finding messages.
- Over-abstraction added in this branch: single-use helper classes, wrappers that only
  forward arguments, config options nothing reads.
- Anything else inconsistent with the style of the file it lives in.

## Do NOT remove (deliberate safety design)

- Code that returns a `CANNOT_ASSESS` finding when an input is missing, unparseable, or out
  of scope (for example no weight for a kidney check, no diagnosis, a paediatric patient).
  These look like defensive checks; they are the product.
- The per-rule `try/except` in the episode evaluator that converts a crashed rule into a
  `CANNOT_ASSESS` finding and marks the evaluation `INCOMPLETE`. It must also log the error.
- Pydantic validators on clinical fields (age, weight, creatinine, dose, duration).
- `evidence`, `source`, `page`, and `provenance` fields and the code that fills them.
- Checks that keep the LLM out of decisions, and checks that block "accept" on a
  `CANNOT_ASSESS` finding or require a reason for an override.
- Labels marking data as synthetic.

If unsure whether a check is slop or safety, keep it and mention it in the summary.
