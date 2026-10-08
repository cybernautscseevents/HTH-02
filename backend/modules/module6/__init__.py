"""
Module 6: Antibiotic Stewardship Checker

Purpose:
- Validate prescribed antibiotics against hospital antibiotic policy.
- Use structured JSON hospital policy with fallback clinical guidelines.
- Classify antibiotic spectrum and check appropriateness for diagnosis.
- Provide clinical reasoning via Mistral LLM (optional, graceful fallback).

Key Functions:
- check_antibiotic_stewardship(drug_list, diagnosis): Main stewardship check.
- check_from_module_outputs(module3, module4): Convenience wrapper.
- reset_cache(): Reload policy data from disk.
"""

from .antibiotic_stewardship import (
    check_antibiotic_stewardship,
    check_from_module_outputs,
    reset_cache,
)

__all__ = [
    "check_antibiotic_stewardship",
    "check_from_module_outputs",
    "reset_cache",
]
