"""Culture-driven checks (C1-C9) that run on the whole episode.

Culture rules speak only when they have something to say: a rule that does not apply returns
no findings. A culture that was never sent is never treated as negative, and nothing here
stops or switches a drug on its own; findings are suggestions for the pharmacist.
"""

from collections.abc import Callable, Iterator
from datetime import timedelta

from . import config
from .rules import RuleContext, allergy_classes, is_identified, matching_allergy
from .schemas import (
    SIR,
    AllergyStatus,
    AwareTier,
    CultureStatus,
    DrugOrder,
    Evidence,
    Finding,
    Isolate,
    Outcome,
    Severity,
    Specimen,
    Suggestion,
)
from .timeout import first_antibiotic_start

CultureRule = Callable[[RuleContext], tuple[Finding, ...]]

INTRINSIC_EVIDENCE = Evidence(
    source_id="amrie-expected-resistance",
    title="Expected resistant phenotypes, CLSI rules (WHONET AMRIE ExpectedResistancePhenotypes)",
)


def _active_antibiotics(ctx: RuleContext) -> list[DrugOrder]:
    return [
        o for o in ctx.episode.orders if is_identified(o) and ctx.catalog.is_antibiotic(o.generic)
    ]


def _final_isolates(ctx: RuleContext) -> Iterator[tuple[Specimen, Isolate]]:
    for spec in ctx.episode.specimens:
        if spec.status is CultureStatus.FINAL:
            for iso in spec.isolates:
                if not iso.probable_contaminant:
                    yield spec, iso


def _result(isolate: Isolate, generic: str) -> SIR | None:
    return next((s.result for s in isolate.susceptibilities if s.agent == generic), None)


def _lab_evidence(spec: Specimen, iso: Isolate) -> Evidence:
    return Evidence(
        source_id=f"specimen:{spec.id}", title=f"{spec.specimen_type} culture: {iso.organism}"
    )


def check_culture_sent(ctx: RuleContext) -> tuple[Finding, ...]:
    """C1: a culture should be sent before Watch/Reserve therapy when the syndrome needs one."""
    if ctx.syndrome is None or not ctx.syndrome.culture_required:
        return ()
    if any(s.status is not CultureStatus.NOT_SENT for s in ctx.episode.specimens):
        return ()
    broad = [
        o
        for o in _active_antibiotics(ctx)
        if ctx.catalog.aware_tier(o.generic, o.route) in (AwareTier.WATCH, AwareTier.RESERVE)
    ]
    if not broad:
        return ()
    names = ", ".join(o.generic for o in broad)
    return (
        Finding(
            rule_id="C1_CULTURE_BEFORE_WATCH",
            outcome=Outcome.FLAG,
            severity=Severity.MODERATE,
            message=f"No culture sent before starting {names} for {ctx.syndrome.name.lower()}.",
            evidence=(ctx.syndrome.evidence,),
            suggestion=Suggestion(
                action="send_culture",
                detail="Collect a culture before or as soon as possible after the first dose.",
            ),
        ),
    )


def check_bug_drug_mismatch(ctx: RuleContext) -> tuple[Finding, ...]:
    """C3: the isolated organism is resistant, or intrinsically resistant, to a current drug."""
    findings = []
    for order in _active_antibiotics(ctx):
        for spec, iso in _final_isolates(ctx):
            intrinsic = ctx.catalog.intrinsically_resistant(iso.organism, order.generic)
            if not intrinsic and _result(iso, order.generic) is not SIR.R:
                continue
            reason = "is intrinsically resistant to" if intrinsic else "tested resistant to"
            evidence = (_lab_evidence(spec, iso),) + ((INTRINSIC_EVIDENCE,) if intrinsic else ())
            findings.append(
                Finding(
                    rule_id="C3_BUG_DRUG_MISMATCH",
                    outcome=Outcome.FLAG,
                    severity=Severity.HIGH,
                    order_id=order.id,
                    message=f"{iso.organism} {reason} {order.generic}; therapy is likely inactive.",
                    evidence=evidence,
                    suggestion=Suggestion(
                        action="switch", detail="Choose an agent the organism is susceptible to."
                    ),
                )
            )
    return tuple(findings)


def _blocked_by_allergy(ctx: RuleContext, generic: str) -> bool:
    """A step-down option is unusable if it matches an allergy or allergy status is unknown."""
    patient = ctx.episode.patient
    if patient.allergy_status is AllergyStatus.UNKNOWN:
        return bool(allergy_classes(generic))
    return matching_allergy(patient, generic) is not None


def check_de_escalation(ctx: RuleContext) -> tuple[Finding, ...]:
    """C4: suggest the narrowest guideline Access drug every isolate is susceptible to."""
    isolates = [iso for _, iso in _final_isolates(ctx)]
    if ctx.syndrome is None or not isolates:
        return ()
    findings = []
    for order in _active_antibiotics(ctx):
        tier = ctx.catalog.aware_tier(order.generic, order.route)
        if tier not in (AwareTier.WATCH, AwareTier.RESERVE):
            continue
        for regimen in (*ctx.syndrome.first_line, *ctx.syndrome.alternatives):
            candidate = regimen.generic
            if (
                candidate == order.generic
                or ctx.catalog.aware_tier(candidate, regimen.route) is not AwareTier.ACCESS
                or (order.route is not None and regimen.route != order.route)
                or _blocked_by_allergy(ctx, candidate)
                or not all(
                    _result(iso, candidate) is SIR.S
                    and not ctx.catalog.intrinsically_resistant(iso.organism, candidate)
                    for iso in isolates
                )
            ):
                continue
            findings.append(
                Finding(
                    rule_id="C4_DE_ESCALATE",
                    outcome=Outcome.FLAG,
                    severity=Severity.MODERATE,
                    order_id=order.id,
                    message=f"Culture shows susceptibility to Access-tier {candidate}; "
                    f"consider stepping down from {order.generic}.",
                    evidence=(regimen.evidence,),
                    suggestion=Suggestion(
                        action="switch",
                        drug=candidate,
                        detail=f"Step down to {candidate} if clinically stable.",
                    ),
                )
            )
            break
    return tuple(findings)


def check_no_growth(ctx: RuleContext) -> tuple[Finding, ...]:
    """C5: no growth after the time-out threshold; the clinician decides whether to stop."""
    start = first_antibiotic_start(ctx.episode, ctx.catalog)
    if start is None or ctx.now - start < timedelta(hours=config.TIMEOUT_HOURS):
        return ()
    return tuple(
        Finding(
            rule_id="C5_NO_GROWTH",
            outcome=Outcome.FLAG,
            severity=Severity.MODERATE,
            message=f"{spec.specimen_type.capitalize()} culture shows no growth "
            f"{config.TIMEOUT_HOURS:g}+ hours after antibiotics started.",
            suggestion=Suggestion(
                action="provide_input",
                detail="Clinician to review whether antibiotics are still needed.",
            ),
        )
        for spec in ctx.episode.specimens
        if spec.status is CultureStatus.NO_GROWTH
    )


def check_contaminants(ctx: RuleContext) -> tuple[Finding, ...]:
    """C6: probable contaminants are reported and excluded from step-down decisions."""
    return tuple(
        Finding(
            rule_id="C6_CONTAMINANT",
            outcome=Outcome.FLAG,
            severity=Severity.LOW,
            message=f"{iso.organism} in {spec.specimen_type} is a probable contaminant and was not "
            "used for step-down suggestions.",
            evidence=(_lab_evidence(spec, iso),),
        )
        for spec in ctx.episode.specimens
        if spec.status is CultureStatus.FINAL
        for iso in spec.isolates
        if iso.probable_contaminant
    )


def check_intermediate(ctx: RuleContext) -> tuple[Finding, ...]:
    """C7: an intermediate result is not treated as susceptible."""
    return tuple(
        Finding(
            rule_id="C7_INTERMEDIATE",
            outcome=Outcome.FLAG,
            severity=Severity.MODERATE,
            order_id=order.id,
            message=f"{iso.organism} is intermediate to {order.generic}; not treated as "
            "susceptible.",
            evidence=(_lab_evidence(spec, iso),),
        )
        for order in _active_antibiotics(ctx)
        for spec, iso in _final_isolates(ctx)
        if _result(iso, order.generic) is SIR.I
    )


def check_not_tested(ctx: RuleContext) -> tuple[Finding, ...]:
    """C8: a current drug missing from the susceptibility panel cannot be assessed."""
    return tuple(
        Finding(
            rule_id="C8_NOT_TESTED",
            outcome=Outcome.CANNOT_ASSESS,
            severity=Severity.MODERATE,
            order_id=order.id,
            message=f"{order.generic} was not tested against {iso.organism}.",
            evidence=(_lab_evidence(spec, iso),),
            missing_inputs=("susceptibility",),
        )
        for order in _active_antibiotics(ctx)
        for spec, iso in _final_isolates(ctx)
        if _result(iso, order.generic) is None
        and not ctx.catalog.intrinsically_resistant(iso.organism, order.generic)
    )


def check_unknown_organism(ctx: RuleContext) -> tuple[Finding, ...]:
    """C9: an organism missing from the reference list has no intrinsic resistance check.

    The intrinsic resistance lookup answers "no" for organisms it does not know, so C3 and C8
    would otherwise read an unknown organism as having no intrinsic resistance.
    """
    return tuple(
        Finding(
            rule_id="C9_ORGANISM_UNKNOWN",
            outcome=Outcome.CANNOT_ASSESS,
            severity=Severity.MODERATE,
            message=f"'{iso.organism}' is not in the organism reference list; intrinsic "
            "resistance was not checked. Record the full scientific name.",
            evidence=(_lab_evidence(spec, iso),),
            missing_inputs=("organism_name",),
        )
        for spec, iso in _final_isolates(ctx)
        if not ctx.catalog.knows_organism(iso.organism)
    )


CULTURE_RULES: tuple[tuple[str, CultureRule], ...] = (
    ("C1_CULTURE_BEFORE_WATCH", check_culture_sent),
    ("C3_BUG_DRUG_MISMATCH", check_bug_drug_mismatch),
    ("C4_DE_ESCALATE", check_de_escalation),
    ("C5_NO_GROWTH", check_no_growth),
    ("C6_CONTAMINANT", check_contaminants),
    ("C7_INTERMEDIATE", check_intermediate),
    ("C8_NOT_TESTED", check_not_tested),
    ("C9_ORGANISM_UNKNOWN", check_unknown_organism),
)
