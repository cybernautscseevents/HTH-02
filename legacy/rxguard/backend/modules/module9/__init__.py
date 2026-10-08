"""
Module 9: Pregnancy Safety Checker

Purpose:
- Check drug safety in pregnancy using FDA PLLR (Pregnancy and Lactation Labeling Rule).
- Evaluate teratogenicity risk, lactation risk, and trimester-specific concerns.
- Provide evidence-based recommendations for pregnant/lactating patients.

Key Functions:
- check_pregnancy_safety(drug_list, is_pregnant, trimester): Main safety check.
"""

from .pregnancy_safety import (
    check_pregnancy_safety,
    check_from_module_outputs,
)

__all__ = [
    "check_pregnancy_safety",
    "check_from_module_outputs",
]
