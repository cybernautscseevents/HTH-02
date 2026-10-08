"""Antibiotic time-out: a structured review once culture results are usually available.

Guidelines recommend reassessing empiric therapy 48-72 hours after the first dose. The
threshold lives in config.TIMEOUT_HOURS.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from . import config
from .ports import DrugCatalog
from .rules import is_identified
from .schemas import Episode, ReviewPhase, TreatmentPlanSignOff

TIMEOUT_DONE = "TIMEOUT_DONE"  # legacy review reason; no longer completes a timeout


def first_antibiotic_start(episode: Episode, catalog: DrugCatalog) -> datetime | None:
    """Earliest start time among identified antibiotic orders."""
    starts = [
        o.started_at
        for o in episode.orders
        if is_identified(o) and catalog.is_antibiotic(o.generic)
    ]
    return min(starts, default=None)


def is_timeout_due(
    episode: Episode,
    now: datetime,
    sign_offs: Iterable[TreatmentPlanSignOff],
    catalog: DrugCatalog,
) -> bool:
    """True after the threshold until a signed timeout treatment plan exists."""
    start = first_antibiotic_start(episode, catalog)
    if start is None or now - start < timedelta(hours=config.TIMEOUT_HOURS):
        return False
    return not any(
        plan.episode_id == episode.id
        and getattr(plan, "phase", None) is ReviewPhase.ANTIBIOTIC_TIMEOUT_48H
        for plan in sign_offs
    )
