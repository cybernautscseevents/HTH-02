"""ICMR AMRSN surveillance table: advisory only, exact matching, small samples marked."""

from pathlib import Path

import pytest

from backend.stewardship import config
from backend.stewardship.drugs import Catalog
from backend.stewardship.surveillance import SurveillanceTable


@pytest.fixture(scope="module")
def table() -> SurveillanceTable:
    return SurveillanceTable.load(Catalog.load())


def test_rows_keep_counts_source_and_context(table):
    rows = table.lookup("nitrofurantoin", organism="Escherichia coli", specimen="urine")
    opd = next(r for r in rows if r.context == "OPD")
    assert (opd.susceptible_count, opd.tested_count, opd.susceptibility_percent) == (
        2504,
        2891,
        86.6,
    )
    assert opd.source_section == "Table 2.11" and opd.source_page == "64"
    assert "2504/2891 isolates" in opd.summary and "ICMR AMRSN 2023" in opd.summary


def test_rows_are_never_pooled_across_contexts(table):
    rows = table.lookup("nitrofurantoin", organism="Escherichia coli", specimen="urine")
    assert len(rows) > 1 and len({(r.context, r.source_section) for r in rows}) == len(rows)


def test_matching_is_exact_not_substring(table):
    assert table.lookup("nitrofurantoin", organism="coli") == ()
    assert table.lookup("nitrofurantoin", organism="Escherichia coli", specimen="urin") == ()


def test_fewer_than_threshold_isolates_is_limited_evidence(table):
    small = [r for r in table.rows if r.tested_count < config.SURVEILLANCE_MIN_ISOLATES]
    assert small and all(r.limited_evidence for r in small)
    assert "Limited evidence" in small[0].summary
    assert not any(r.limited_evidence for r in table.rows if r.tested_count >= 30)


def test_inconsistent_rows_are_skipped_with_the_reason(table):
    reasons = [reason for _, reason in table.skipped if "disagrees" in reason]
    assert len(reasons) == 3 and any("195/198" in r for r in reasons)


def test_drug_names_are_matched_exactly_or_skipped(table):
    generics = {r.antibiotic: r.generic for r in table.rows}
    assert generics["Vancomyc in"] == "vancomycin"  # PDF split word
    assert generics["Colistin*"] == "colistin"  # source low-count marker
    skipped = {raw["antibiotic"] for raw, _ in table.skipped}
    assert {"Gentamicin HL", "Piperacillin-tazobacta", "Fluconazole"} <= skipped


def test_surveillance_is_not_an_engine_input():
    package = Path(config.__file__).parent
    for module in ("rules.py", "culture.py", "episode.py", "service.py", "api.py"):
        assert "surveillance" not in (package / module).read_text(), module
