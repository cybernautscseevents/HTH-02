#!/usr/bin/env python3
"""
backend/modules/module3/test_ocr_normalization.py
==================================================
Unit tests for Module 3 OCR Normalization Safeguards.

Tests cover:
1. Different-Generic LASA (Look-Alike Sound-Alike) Collision Safeguard (Rule 5):
   - "Apeelo" (OCR misread when ground truth is "Apeclo") must resolve to AMBIGUOUS
     instead of a confident WRONG acceptance, because Apeelo (apremilast) and
     Apeclo (aceclofenac) have different generics and edit distance <= 2.
   - Clean "Apeclo" read: documents and tests behavior in isolated normalization
     (flags AMBIGUOUS due to mutual 1-edit collision with Apeelo) vs end-to-end
     OCR pipeline behavior where exact matches bypass normalization.
2. Same-Generic Family Ambiguity Safeguard (Rule 4):
   - Verifies that existing same-generic brand pairs (Montelar/Montelon -> montelukast,
     Bilau/Bilaxe -> bilastine, Inderen/Indever -> propranolol) continue to resolve
     to AMBIGUOUS without regressions under both GLM-OCR (0.82) and PaddleOCR (0.72)
     threshold configurations.
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import unittest
from backend.modules.module3.ocr_normalization import (
    NormConfig,
    normalize_ocr_token,
)
from benchmarks.normalization_benchmark import (
    OUTCOME_AMBIGUOUS,
    ambiguous_contains_gt,
    classify_result,
)


class TestOCRNormalizationSafeguards(unittest.TestCase):
    """Test suite for OCR normalization decision rules and safety safeguards."""

    def setUp(self):
        # Calibrated configurations for both target models
        self.glm_config = NormConfig(confidence_threshold=0.82, ambiguity_gap=0.10)
        self.paddle_config = NormConfig(confidence_threshold=0.72, ambiguity_gap=0.10)

    def test_different_generic_lasa_apeelo_misread(self):
        """
        Test that when OCR outputs 'Apeelo' (GT is 'Apeclo'), normalization flags AMBIGUOUS.

        Apeelo maps to apremilast (PDE4 inhibitor) and Apeclo maps to aceclofenac (NSAID).
        Their edit distance is 1 ('e' vs 'c'). Because they resolve to different generics,
        Rule 5 must trigger and return AMBIGUOUS, preventing a dangerous wrong-generic
        drug identification.
        """
        for config, model_name in [
            (self.glm_config, "GLM-OCR"),
            (self.paddle_config, "PaddleOCR"),
        ]:
            with self.subTest(model=model_name):
                result = normalize_ocr_token("Apeelo", config=config)

                # Must not be ACCEPTED as Apeelo (which would be WRONG against GT Apeclo)
                self.assertEqual(
                    result.status,
                    "AMBIGUOUS",
                    f"Expected AMBIGUOUS for 'Apeelo' under {model_name}, got {result.status}",
                )
                self.assertIsNone(result.matched_name)

                # Verify top 2 candidates are Apeelo and Apeclo
                candidate_names = [c.brand_name for c in result.candidates[:2]]
                self.assertIn("Apeelo", candidate_names)
                self.assertIn("Apeclo", candidate_names)

                # Verify different generics
                generics = {c.generic_name for c in result.candidates[:2]}
                self.assertIn("apremilast", generics)
                self.assertIn("aceclofenac", generics)

                # Verify benchmark outcome classification against ground truth 'Apeclo'
                outcome = classify_result(result, "Apeclo")
                self.assertEqual(
                    outcome,
                    OUTCOME_AMBIGUOUS,
                    f"Outcome under {model_name} should be AMBIGUOUS, got {outcome}",
                )

                # Ground truth 'Apeclo' must be present in the ambiguous candidate pool
                self.assertTrue(
                    ambiguous_contains_gt(result, "Apeclo"),
                    f"Ground truth 'Apeclo' should be in candidate list for {model_name}",
                )

    def test_clean_apeclo_read_behavior(self):
        """
        Document and test behavior for a clean 'Apeclo' read.

        In isolated normalization:
        Because 'Apeelo' (apremilast) and 'Apeclo' (aceclofenac) are mutual 1-letter
        substitutions, an isolated 'Apeclo' token without external context also triggers
        the Rule 5 safeguard (AMBIGUOUS) to guard against misreading handwritten 'e' as 'c'.

        In end-to-end pipeline:
        If OCR outputs 'Apeclo' and ground truth is 'Apeclo', OCR exact match evaluates
        to True, bypassing normalization entirely.
        """
        for config, model_name in [
            (self.glm_config, "GLM-OCR"),
            (self.paddle_config, "PaddleOCR"),
        ]:
            with self.subTest(model=model_name):
                result = normalize_ocr_token("Apeclo", config=config)

                # In isolated normalization, safeguard triggers symmetrically
                self.assertEqual(
                    result.status,
                    "AMBIGUOUS",
                    f"Expected AMBIGUOUS for isolated 'Apeclo' under {model_name}",
                )

                # Candidate pool contains both LASA collision partners
                candidate_brands = [c.brand_name for c in result.candidates[:2]]
                self.assertIn("Apeclo", candidate_brands)
                self.assertIn("Apeelo", candidate_brands)

                # When evaluated against ground truth 'Apeclo'
                self.assertTrue(
                    ambiguous_contains_gt(result, "Apeclo"),
                    "True label 'Apeclo' must be present among ambiguous candidates",
                )

    def test_same_generic_pairs_no_regression(self):
        """
        Verify that existing same-generic brand pairs resolve to AMBIGUOUS with no regressions.

        Tested pairs:
        - Montelar / Montelon -> montelukast
        - Bilau / Bilaxe -> bilastine (via close match with Bilax)
        - Inderen / Indever -> propranolol
        """
        test_cases = [
            ("Montelar", "montelukast"),
            ("Montelon", "montelukast"),
            ("Bilau", "bilastine"),
            ("Bilaxe", "bilastine"),
            ("Inderen", "propranolol"),
            ("Indever", "propranolol"),
        ]

        for config, model_name in [
            (self.glm_config, "GLM-OCR"),
            (self.paddle_config, "PaddleOCR"),
        ]:
            for token, expected_generic in test_cases:
                with self.subTest(model=model_name, token=token):
                    result = normalize_ocr_token(token, config=config)

                    self.assertEqual(
                        result.status,
                        "AMBIGUOUS",
                        f"Expected AMBIGUOUS for {token} under {model_name}, got {result.status}",
                    )
                    # Verify the generic matches expected active ingredient
                    self.assertEqual(
                        result.candidates[0].generic_name,
                        expected_generic,
                        f"Generic mismatch for {token} under {model_name}",
                    )


if __name__ == "__main__":
    unittest.main()
