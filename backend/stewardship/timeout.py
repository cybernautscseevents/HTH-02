"""Antibiotic time-out: a structured review once culture results are usually available.

Guidelines recommend reassessing empiric therapy 48-72 hours after the first dose. The
threshold lives in config.TIMEOUT_HOURS.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from . import config
from .ports import DrugCatalog
from .rules import is_identified
from .schemas import Episode, Review

TIMEOUT_DONE = "TIMEOUT_DONE"


def first_antibiotic_start(episode: Episode, catalog: DrugCatalog) -> datetime | None:
    """Earliest start time among identified antibiotic orders."""
    starts = [
        o.started_at
        for o in episode.orders
        if is_identified(o) and catalog.is_antibiotic(o.generic)
    ]
    return min(starts, default=None)


def is_timeout_due(
    episode: Episode, now: datetime, reviews: Iterable[Review], catalog: DrugCatalog
) -> bool:
    """True once the threshold has passed and no time-out review is recorded for the episode."""
    start = first_antibiotic_start(episode, catalog)
    if start is None or now - start < timedelta(hours=config.TIMEOUT_HOURS):
        return False
    return not any(r.episode_id == episode.id and r.reason_code == TIMEOUT_DONE for r in reviews)
