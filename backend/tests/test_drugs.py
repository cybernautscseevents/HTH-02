import pytest

from backend.stewardship.drugs import Catalog
from backend.stewardship.schemas import AwareTier, NormStatus


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


def test_aware_tiers_come_from_the_table(catalog):
    assert catalog.aware_tier("amoxicillin") is AwareTier.ACCESS
    assert catalog.aware_tier("ceftriaxone") is AwareTier.WATCH
    assert catalog.aware_tier("linezolid") is AwareTier.RESERVE


def test_unknown_drug_is_not_classified(catalog):
    assert catalog.aware_tier("paracetamol") is AwareTier.NOT_CLASSIFIED


def test_only_systemic_antibacterials_are_antibiotics(catalog):
    assert catalog.is_antibiotic("amoxicillin")
    assert not catalog.is_antibiotic("paracetamol")


def test_intrinsic_resistance_lookup(catalog):
    assert catalog.intrinsically_resistant("Pseudomonas aeruginosa", "ceftriaxone")
    assert catalog.intrinsically_resistant("enterococcus faecalis", "cephalexin")
    assert not catalog.intrinsically_resistant("Escherichia coli", "ceftriaxone")


def test_generic_name_with_form_and_strength_is_accepted(catalog):
    result = catalog.normalize("Tab. Amoxicillin 500 mg TDS")
    assert result.status is NormStatus.ACCEPTED
    assert result.generic == "amoxicillin"


def test_synonym_maps_to_table_name(catalog):
    assert catalog.normalize("Co-trimoxazole 960 mg").generic == "trimethoprim/sulfamethoxazole"
    assert catalog.normalize("amoxicillin + clavulanate").generic == ("amoxicillin/clavulanic acid")


def test_brand_is_mapped_to_generic(catalog):
    result = catalog.normalize("Clavutil 625")
    assert result.status is NormStatus.ACCEPTED
    assert result.generic == "amoxicillin/clavulanic acid"
    assert result.brand == "clavutil"


def test_misspelling_is_never_accepted(catalog):
    result = catalog.normalize("amoxicilin 500")
    assert result.status is NormStatus.AMBIGUOUS
    assert result.generic is None
    assert "amoxicillin" in result.candidates


def test_unknown_name_has_no_match(catalog):
    assert catalog.normalize("zzqx 10 mg").status is NormStatus.NO_MATCH


def test_brand_shared_by_two_generics_is_ambiguous():
    catalog = Catalog(
        tiers={"cefixime": AwareTier.WATCH, "cefuroxime": AwareTier.WATCH},
        brands={"Cefo": frozenset({"cefixime", "cefuroxime"})},
        intrinsic=frozenset(),
    )
    result = catalog.normalize("Cefo 200")
    assert result.status is NormStatus.AMBIGUOUS
    assert result.candidates == ("cefixime", "cefuroxime")
