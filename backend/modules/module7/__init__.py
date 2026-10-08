"""Module 7: Dose Adjustment

Provides rule-based dose adjustment checks using offline FDA label JSON data.
"""

from .dose_adjustment import check_dose_adjustment, check_from_module_outputs, get_drug_label_info

__all__ = [
    "check_dose_adjustment",
    "check_from_module_outputs",
    "get_drug_label_info",
]
