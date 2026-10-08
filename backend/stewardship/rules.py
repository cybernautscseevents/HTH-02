"""Per-prescription stewardship checks (R0-R6).

Each rule is a pure function of a RuleContext and one drug order, and returns exactly one
Finding. A rule never guesses: when an input it needs is missing or out of scope, it returns
CANNOT_ASSESS and names the missing input, so a gap is visible to the pharmacist instead of
looking like a pass.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from . import config
from .ports import DrugCatalog, RenalChecker, RulePack
from .schemas import (
    AllergyStatus,
    AwareTier,
    DrugOrder,
    DrugRegimen,
    Episode,
    Evidence,
    Finding,
    NormStatus,
    Outcome,
    Patient,
    Severity,
    Suggestion,
    SyndromeRule,
)

AWARE_EVIDENCE = Evidence(
    source_id="who-aware",
    title="WHO AWaRe classification of antibiotics (via WHONET AMRIE antibiotic table)",
)


@dataclass(frozen=True)
class RuleContext:
    episode: Episode
    rulepack: RulePack
    catalog: DrugCatalog
    renal: RenalChecker
    now: datetime
    syndrome: SyndromeRule | None

    @classmethod
    def build(
        cls,
        *,
        episode: Episode,
        rulepack: RulePack,
        catalog: DrugCatalog,
        renal: RenalChecker,
        now: datetime,
    ) -> "RuleContext":
        """Resolve the episode's syndrome once so every rule sees the same guideline entry."""
        syndrome = rulepack.syndrome(episode.syndrome_code) if episode.syndrome_code else None
        return cls(episode, rulepack, catalog, renal, now, syndrome)


OrderRule = Callable[[RuleContext, DrugOrder], Finding]


def is_identified(order: DrugOrder) -> bool:
    return order.generic is not None and order.norm_status in (
        NormStatus.ACCEPTED,
        NormStatus.CONFIRMED,
    )


def allergy_classes(generic: str) -> frozenset[str]:
    """Beta-lactam classes a drug belongs to, used for allergy matching."""
    classes = set()
    if "cillin" in generic:
        classes.add("penicillin")
    if generic.startswith(("cef", "ceph")):
        classes.add("cephalosporin")
    if "penem" in generic:
        classes.add("carbapenem")
    return frozenset(classes)


def matching_allergy(patient: Patient, generic: str) -> str | None:
    """Documented allergy that matches the drug by name or beta-lactam class, if any."""
    classes = allergy_classes(generic)
    for allergy in (a.strip().lower() for a in patient.allergies):
        if allergy == generic or allergy in classes or allergy_classes(allergy) & classes:
            return allergy
    return None


def regimen_for(syndrome: SyndromeRule, order: DrugOrder) -> DrugRegimen | None:
    """Guideline regimen matching the order's drug and route.

    Without a route, a regimen is returned only when the drug has exactly one listed route.
    """
    regimens = (*syndrome.first_line, *syndrome.alternatives)
    matches = [r for r in regimens if r.generic == order.generic]
    if order.route is not None:
        matches = [r for r in matches if r.route == order.route]
    return matches[0] if len(matches) == 1 else None


def _finding(
    rule_id: str, outcome: Outcome, severity: Severity, order: DrugOrder, message: str, **extra
) -> Finding:
    return Finding(
        rule_id=rule_id,
        outcome=outcome,
        severity=severity,
        order_id=order.id,
        message=message,
        **extra,
    )


def _syndrome_missing(rule_id: str, ctx: RuleContext, order: DrugOrder) -> Finding:
    if ctx.episode.syndrome_code is None:
        message = "No infection syndrome recorded; guideline checks cannot run."
    else:
        message = f"No guideline entry for syndrome '{ctx.episode.syndrome_code}'."
    return _finding(
        rule_id,
        Outcome.CANNOT_ASSESS,
        Severity.MODERATE,
        order,
        message,
        missing_inputs=("syndrome",),
    )


def check_identified(ctx: RuleContext, order: DrugOrder) -> Finding:
    """R0: the drug must be identified with confidence before any other check runs."""
    rule_id = "R0_IDENTIFIED"
    if is_identified(order):
        return _finding(
            rule_id,
            Outcome.PASS,
            Severity.INFO,
            order,
            f"'{order.raw_text}' identified as {order.generic}.",
        )
    if order.norm_status is NormStatus.AMBIGUOUS:
        reason = f"matches more than one drug: {', '.join(order.norm_candidates)}"
    else:
        reason = "does not match any drug in the lexicon"
    return _finding(
        rule_id,
        Outcome.CANNOT_ASSESS,
        Severity.HIGH,
        order,
        f"'{order.raw_text}' {reason}. No checks were run for this order.",
        suggestion=Suggestion(
            action="confirm_drug",
            detail=f"Confirm the intended drug. Candidates: "
            f"{', '.join(order.norm_candidates) or 'none'}.",
        ),
        missing_inputs=("drug_identity",),
    )


def check_indication(ctx: RuleContext, order: DrugOrder) -> Finding:
    """R1: is this drug recommended for the episode's syndrome?"""
    rule_id = "R1_INDICATION"
    syndrome = ctx.syndrome
    if syndrome is None:
        return _syndrome_missing(rule_id, ctx, order)
    if not syndrome.antibiotics_indicated:
        return _finding(
            rule_id,
            Outcome.FLAG,
            Severity.HIGH,
            order,
            f"Antibiotics are not indicated for {syndrome.name.lower()}.",
            evidence=(syndrome.evidence,),
            suggestion=Suggestion(
                action="stop", drug=order.generic, detail="Review whether an antibiotic is needed."
            ),
        )
    first = next((r for r in syndrome.first_line if r.generic == order.generic), None)
    if first is not None:
        return _finding(
            rule_id,
            Outcome.PASS,
            Severity.INFO,
            order,
            f"{order.generic} is first-line for {syndrome.name.lower()}.",
            evidence=(first.evidence,),
        )
    alternative = next((r for r in syndrome.alternatives if r.generic == order.generic), None)
    preferred = syndrome.first_line[0] if syndrome.first_line else None
    if alternative is not None:
        note = f" First-line is {preferred.generic}." if preferred else ""
        return _finding(
            rule_id,
            Outcome.PASS,
            Severity.INFO,
            order,
            f"{order.generic} is an alternative for {syndrome.name.lower()}.{note}",
            evidence=(alternative.evidence,),
        )
    return _finding(
        rule_id,
        Outcome.FLAG,
        Severity.MODERATE,
        order,
        f"{order.generic} is not listed for {syndrome.name.lower()}.",
        evidence=(syndrome.evidence,),
        suggestion=Suggestion(
            action="switch",
            drug=preferred.generic,
            detail=f"Guideline first-line is {preferred.generic}.",
        )
        if preferred
        else None,
    )


def check_aware(ctx: RuleContext, order: DrugOrder) -> Finding:
    """R2: Reserve drugs need approval; Watch drugs need a reason when an Access drug fits."""
    rule_id = "R2_AWARE"
    tier = ctx.catalog.aware_tier(order.generic)
    if tier is AwareTier.NOT_CLASSIFIED:
        return _finding(
            rule_id,
            Outcome.CANNOT_ASSESS,
            Severity.LOW,
            order,
            f"{order.generic} has no AWaRe classification.",
            missing_inputs=("aware_tier",),
        )
    if tier is AwareTier.RESERVE:
        return _finding(
            rule_id,
            Outcome.FLAG,
            Severity.HIGH,
            order,
            f"{order.generic} is a Reserve antibiotic and requires stewardship approval.",
            evidence=(AWARE_EVIDENCE,),
        )
    if tier is AwareTier.WATCH and ctx.syndrome is not None:
        access = next(
            (
                r
                for r in ctx.syndrome.first_line
                if ctx.catalog.aware_tier(r.generic) is AwareTier.ACCESS
            ),
            None,
        )
        if access is not None:
            return _finding(
                rule_id,
                Outcome.FLAG,
                Severity.MODERATE,
                order,
                f"{order.generic} is a Watch antibiotic; an Access first-line option exists.",
                evidence=(AWARE_EVIDENCE, access.evidence),
                suggestion=Suggestion(
                    action="switch",
                    drug=access.generic,
                    detail=f"Consider Access-tier {access.generic}.",
                ),
            )
    return _finding(
        rule_id,
        Outcome.PASS,
        Severity.INFO,
        order,
        f"{order.generic} is {tier.value.title()} tier.",
        evidence=(AWARE_EVIDENCE,),
    )


def check_dose(ctx: RuleContext, order: DrugOrder) -> Finding:
    """R3: total daily dose must fall within the guideline range for the drug and route."""
    rule_id = "R3_DOSE"
    if ctx.episode.patient.age_years < config.ADULT_AGE_YEARS:
        return _finding(
            rule_id,
            Outcome.CANNOT_ASSESS,
            Severity.MODERATE,
            order,
            "Dose rules cover adults only; paediatric dosing was not checked.",
        )
    missing = tuple(
        name
        for name, value in (("dose_mg", order.dose_mg), ("freq_per_day", order.freq_per_day))
        if value is None
    )
    if missing:
        return _finding(
            rule_id,
            Outcome.CANNOT_ASSESS,
            Severity.MODERATE,
            order,
            "Dose or frequency missing; dose was not checked.",
            missing_inputs=missing,
        )
    if ctx.syndrome is None:
        return _syndrome_missing(rule_id, ctx, order)
    regimen = regimen_for(ctx.syndrome, order)
    if regimen is None:
        return _finding(
            rule_id,
            Outcome.CANNOT_ASSESS,
            Severity.LOW,
            order,
            f"No guideline dose for {order.generic} by this route.",
            missing_inputs=("route",) if order.route is None else (),
        )
    daily = order.dose_mg * order.freq_per_day
    low, high = regimen.daily_dose_mg_min, regimen.daily_dose_mg_max
    range_text = f"{low:g}-{high:g} mg/day"
    if daily > high:
        severity = Severity.HIGH if daily > high * config.HIGH_DOSE_FACTOR else Severity.MODERATE
        message = f"Daily dose {daily:g} mg exceeds the guideline range {range_text}."
    elif daily < low:
        severity = Severity.MODERATE
        message = f"Daily dose {daily:g} mg is below the guideline range {range_text}."
    else:
        return _finding(
            rule_id,
            Outcome.PASS,
            Severity.INFO,
            order,
            f"Daily dose {daily:g} mg is within {range_text}.",
            evidence=(regimen.evidence,),
        )
    return _finding(
        rule_id,
        Outcome.FLAG,
        severity,
        order,
        message,
        evidence=(regimen.evidence,),
        suggestion=Suggestion(
            action="adjust_dose", drug=order.generic, detail=f"Guideline range is {range_text}."
        ),
    )


def check_renal(ctx: RuleContext, order: DrugOrder) -> Finding:
    """R4: kidney-function dosing, delegated to the renal checker."""
    return ctx.renal.check(order, ctx.episode.patient)


def check_duration(ctx: RuleContext, order: DrugOrder) -> Finding:
    """R5: planned duration must fall within the guideline range."""
    rule_id = "R5_DURATION"
    if order.duration_days is None:
        return _finding(
            rule_id,
            Outcome.CANNOT_ASSESS,
            Severity.LOW,
            order,
            "No planned duration recorded.",
            missing_inputs=("duration_days",),
        )
    if ctx.syndrome is None:
        return _syndrome_missing(rule_id, ctx, order)
    regimen = regimen_for(ctx.syndrome, order)
    if regimen is None:
        return _finding(
            rule_id,
            Outcome.CANNOT_ASSESS,
            Severity.LOW,
            order,
            f"No guideline duration for {order.generic} by this route.",
        )
    low, high = regimen.duration_days_min, regimen.duration_days_max
    range_text = f"{low}-{high} days" if low != high else f"{low} days"
    if low <= order.duration_days <= high:
        return _finding(
            rule_id,
            Outcome.PASS,
            Severity.INFO,
            order,
            f"Duration {order.duration_days} days matches the guideline ({range_text}).",
            evidence=(regimen.evidence,),
        )
    too_long = order.duration_days > high
    return _finding(
        rule_id,
        Outcome.FLAG,
        Severity.MODERATE if too_long else Severity.LOW,
        order,
        f"Duration {order.duration_days} days is {'longer' if too_long else 'shorter'} than "
        f"the guideline ({range_text}).",
        evidence=(regimen.evidence,),
        suggestion=Suggestion(
            action="adjust_duration",
            drug=order.generic,
            detail=f"Guideline duration is {range_text}.",
        ),
    )


def check_allergy(ctx: RuleContext, order: DrugOrder) -> Finding:
    """R6: documented allergies, matched by drug name or beta-lactam class."""
    rule_id = "R6_ALLERGY"
    patient = ctx.episode.patient
    classes = allergy_classes(order.generic)
    if patient.allergy_status is AllergyStatus.UNKNOWN:
        return _finding(
            rule_id,
            Outcome.CANNOT_ASSESS,
            Severity.MODERATE if classes else Severity.LOW,
            order,
            "Allergy status unknown" + ("; this is a beta-lactam." if classes else "."),
            missing_inputs=("allergy_status",),
        )
    allergy = matching_allergy(patient, order.generic)
    if allergy is not None:
        return _finding(
            rule_id,
            Outcome.FLAG,
            Severity.HIGH,
            order,
            f"Documented allergy to {allergy}; {order.generic} may be contraindicated.",
        )
    return _finding(
        rule_id, Outcome.PASS, Severity.INFO, order, "No documented allergy matches this drug."
    )


# Run in order for every identified antibiotic order; R0 runs first as a gate.
ORDER_RULES: tuple[tuple[str, OrderRule], ...] = (
    ("R1_INDICATION", check_indication),
    ("R2_AWARE", check_aware),
    ("R3_DOSE", check_dose),
    ("R4_RENAL", check_renal),
    ("R5_DURATION", check_duration),
    ("R6_ALLERGY", check_allergy),
)
