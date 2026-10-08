import pytest

from backend.stewardship.drugs import Catalog
from backend.stewardship.schemas import AwareTier, NormStatus, Route


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


# --- Normalization ---


def test_exact_generic_is_accepted(catalog):
    result = catalog.normalize("Tab. Amoxicillin 500 mg TDS")
    assert (result.status, result.generic) == (NormStatus.ACCEPTED, "amoxicillin")
    assert result.reason == "Exact generic name."


def test_indian_brand_maps_to_generic_with_source(catalog):
    result = catalog.normalize("Augmentin 625 Duo BD x 5 days")
    assert (result.status, result.generic) == (NormStatus.ACCEPTED, "amoxicillin/clavulanic acid")
    assert result.brand == "augmentin"
    assert "india-pharma.gsk.com" in result.reason


def test_indian_pharmacopoeia_spelling_is_an_alias(catalog):
    result = catalog.normalize("Amoxycillin 500mg")
    assert (result.status, result.generic) == (NormStatus.ACCEPTED, "amoxicillin")
    assert "Indian Pharmacopoeia" in result.reason


def test_guideline_name_maps_to_who_name(catalog):
    assert catalog.normalize("Cotrimoxazole 960 mg").generic == "sulfamethoxazole/trimethoprim"
    assert catalog.normalize("Cephalexin 500").generic == "cefalexin"


def test_ocr_misread_brand_is_ambiguous_not_accepted(catalog):
    result = catalog.normalize("Augmentn 625")
    assert result.status is NormStatus.AMBIGUOUS
    assert result.generic is None
    assert "amoxicillin/clavulanic acid" in result.candidates


def test_misspelt_generic_is_never_accepted(catalog):
    result = catalog.normalize("amoxicilin 500")
    assert result.status is NormStatus.AMBIGUOUS
    assert result.generic is None
    assert "amoxicillin" in result.candidates
    assert "not an exact match" in result.reason


def test_unknown_name_has_no_match(catalog):
    result = catalog.normalize("zzqx 10 mg")
    assert result.status is NormStatus.NO_MATCH
    assert result.reason


def test_brand_shared_by_two_generics_is_ambiguous():
    catalog = Catalog(
        tiers={("cefixime", ""): AwareTier.WATCH, ("cefuroxime", ""): AwareTier.WATCH},
        aliases={},
        brands={"Cefo": (frozenset({"cefixime", "cefuroxime"}), "test fixture")},
        intrinsic=frozenset(),
        organisms=frozenset(),
    )
    result = catalog.normalize("Cefo 200")
    assert result.status is NormStatus.AMBIGUOUS
    assert result.candidates == ("cefixime", "cefuroxime")


# --- Antibiotic status and WHO AWaRe 2025 ---


def test_non_antibiotic(catalog):
    assert not catalog.is_antibiotic("paracetamol")
    assert catalog.aware_tier("paracetamol") is AwareTier.NOT_CLASSIFIED


def test_access_watch_reserve(catalog):
    assert catalog.aware_tier("amoxicillin") is AwareTier.ACCESS
    assert catalog.aware_tier("nitrofurantoin") is AwareTier.ACCESS
    assert catalog.aware_tier("ceftriaxone") is AwareTier.WATCH
    assert catalog.aware_tier("linezolid") is AwareTier.RESERVE


def test_cefpodoxime_is_watch_in_who_2025(catalog):
    generic = catalog.normalize("Cefpodoxime 200 mg").generic
    assert generic == "cefpodoxime proxetil"
    assert catalog.aware_tier(generic) is AwareTier.WATCH


def test_route_specific_tier(catalog):
    assert catalog.aware_tier("fosfomycin", Route.PO) is AwareTier.WATCH
    assert catalog.aware_tier("fosfomycin", Route.IV) is AwareTier.RESERVE
    assert catalog.aware_tier("fosfomycin") is AwareTier.NOT_CLASSIFIED


def test_antibiotic_not_classified_by_who_is_still_an_antibiotic(catalog):
    assert catalog.is_antibiotic("bacitracin zinc")
    assert catalog.aware_tier("bacitracin zinc") is AwareTier.NOT_CLASSIFIED


# --- Intrinsic resistance ---


def test_intrinsic_resistance(catalog):
    assert catalog.intrinsically_resistant("Pseudomonas aeruginosa", "ceftriaxone")
    assert catalog.intrinsically_resistant("Enterococcus faecalis", "cefalexin")


def test_organism_without_intrinsic_resistance_to_drug(catalog):
    assert catalog.knows_organism("Escherichia coli")
    assert not catalog.intrinsically_resistant("Escherichia coli", "ceftriaxone")


def test_unknown_organism_is_reported_unknown(catalog):
    assert not catalog.knows_organism("E. coli")
    assert not catalog.knows_organism("Bugus imaginarius")


# --- Review regressions ---


def test_listed_product_words_beside_a_brand_are_accepted(catalog):
    assert catalog.normalize("Augmentin Duo").generic == "amoxicillin/clavulanic acid"
    assert catalog.normalize("I.V. Augmentin 1.2g").generic == "amoxicillin/clavulanic acid"
    assert catalog.normalize("Fortum ES 2g").generic == "ceftazidime"


def test_brand_with_unlisted_words_is_not_accepted(catalog):
    for text in ("Ceftum Plus 500", "Augmentin Metronidazole"):
        result = catalog.normalize(text)
        assert result.status is NormStatus.AMBIGUOUS, text
        assert result.generic is None
        assert "unlisted words" in result.reason


def test_second_drug_on_one_line_is_not_dropped(catalog):
    result = catalog.normalize("Augmentin 625 + Metrogyl 400")
    assert result.status is NormStatus.AMBIGUOUS
    assert result.generic is None
    assert "more than one drug" in result.reason


def test_strength_written_with_plus_is_still_one_drug(catalog):
    result = catalog.normalize("Augmentin 500+125 mg")
    assert result.status is NormStatus.ACCEPTED


def test_unlisted_route_uses_tier_only_when_all_routes_agree(catalog):
    assert catalog.aware_tier("vancomycin", Route.IM) is AwareTier.WATCH
    assert catalog.aware_tier("fosfomycin", Route.IM) is AwareTier.NOT_CLASSIFIED


def test_indian_combination_spelling_is_accepted(catalog):
    result = catalog.normalize("Amoxycillin + Clavulanate 625")
    assert (result.status, result.generic) == (NormStatus.ACCEPTED, "amoxicillin/clavulanic acid")


def test_usan_rifampin_is_the_who_rifampicin(catalog):
    result = catalog.normalize("Rifampin")
    assert (result.status, result.generic) == (NormStatus.ACCEPTED, "rifampicin")
    assert "J04AB02" in result.reason
