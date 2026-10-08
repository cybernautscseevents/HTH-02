"""Deterministic drug–drug interaction checking against the local DrugBank export.

DDI is an evidence lookup, never a clinical decision. DrugBank either reports an interaction
for a pair or it does not; anything the source cannot answer is CANNOT_ASSESS — never "safe".
"No interaction reported" means only that the configured source does not report one.

The provider reads a one-time SQLite index built from the local DrugBank XML export
(config.DRUGBANK_XML_PATH, licensed data that is never committed) into config.DDI_INDEX_PATH;
lookups never parse the XML. No model, keyword severity guess or drug–disease layer is
involved: severity is reported only when the source explicitly provides it (this export does
not, so a found interaction carries severity "unknown" and needs_review=True).

Integration: StewardshipService calls check_pairs() after evaluate_episode() and appends the
resulting ordinary Findings to the report. R0–R6 and the culture rules are untouched, and a
failing provider can never take the evaluation down — every failure becomes CANNOT_ASSESS.
"""

import itertools
import logging
import os
import sqlite3
import threading
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from . import config
from .drugs import _key
from .rules import is_identified
from .schemas import (
    DataProvenance,
    DrugOrder,
    Episode,
    Evidence,
    Finding,
    NormStatus,
    Outcome,
    Severity,
)

logger = logging.getLogger(__name__)

_NS = "{http://www.drugbank.ca}"

DDI_INTERACTION = "DDI_INTERACTION"
DDI_NO_INTERACTION = "DDI_NO_INTERACTION"
DDI_CANNOT_ASSESS = "DDI_CANNOT_ASSESS"

SOURCE_NAME = "DrugBank"


class DDIStatus(StrEnum):
    INTERACTION_FOUND = "INTERACTION_FOUND"
    NO_INTERACTION_REPORTED_BY_SOURCE = "NO_INTERACTION_REPORTED_BY_SOURCE"
    CANNOT_ASSESS = "CANNOT_ASSESS"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DDIResult(_Model):
    """One pair's lookup result. Also carried to the UI as FindingView.ddi.

    severity is major|moderate|minor|unknown and is only ever what the source states; this
    export has no structured severity, so a found interaction is "unknown", never guessed.
    """

    type: str = "DDI"
    drug_a: str | None = None
    drug_b: str | None = None
    status: DDIStatus
    severity: str = "unknown"
    mechanism: str | None = None
    explanation: str | None = None
    action: str | None = None
    description: str | None = None  # the source's own interaction text
    reason: str | None = None  # why CANNOT_ASSESS
    source: str = SOURCE_NAME
    source_version: str | None = None
    evidence: str | None = None
    needs_review: bool = False

    @field_validator("severity")
    @classmethod
    def _only_source_severities(cls, value: str) -> str:
        # Anything outside the four allowed values is not a severity the source stated,
        # so it is reported as unknown rather than passed through or guessed at.
        return value if value in ("major", "moderate", "minor", "unknown") else "unknown"

    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data: dict) -> dict:
        if isinstance(data, dict):
            status = data.get("status")
            desc = data.get("description")
            if status == DDIStatus.INTERACTION_FOUND or status == "INTERACTION_FOUND":
                if not data.get("mechanism") and desc:
                    data["mechanism"] = desc
                if not data.get("explanation") and desc:
                    data["explanation"] = desc
                if not data.get("evidence") and desc:
                    data["evidence"] = desc
                if not data.get("action"):
                    data["action"] = (
                        "Review the reported interaction with the pharmacist before the drugs are co-administered."
                    )
            elif status == DDIStatus.CANNOT_ASSESS or status == "CANNOT_ASSESS":
                if not data.get("action"):
                    data["action"] = (
                        "Confirm the drug identity, or review the drug's interactions manually; DrugBank could not answer this pair."
                    )
                if not data.get("explanation"):
                    data["explanation"] = data.get("reason")
        return data


class DDIFinding(NamedTuple):
    """A finding for the report plus the structured pair result behind it."""

    finding: Finding
    result: DDIResult


class PairChecks(NamedTuple):
    findings: tuple[DDIFinding, ...]
    crashed: bool  # a provider raised: the evaluation is marked INCOMPLETE, like the engine


class DDIProvider(Protocol):
    def lookup_pair(self, drug_a: str, drug_b: str) -> DDIResult: ...


# Display severity for a found interaction. The source's own severity (major/moderate/minor)
# maps directly; "unknown" is an attention level for review, not a clinical severity claim —
# the DDIResult keeps severity="unknown" and needs_review=True.
_FINDING_SEVERITY = {
    "major": Severity.HIGH,
    "moderate": Severity.MODERATE,
    "minor": Severity.LOW,
    "unknown": Severity.MODERATE,
}

_MAX_DESCRIPTION = 400


def _truncate(text: str) -> str:
    if len(text) <= _MAX_DESCRIPTION:
        return text
    cut = text[:_MAX_DESCRIPTION].rsplit(" ", 1)[0]
    return cut + " …"


def _pair_id(drug_id_a: str, drug_id_b: str) -> tuple[str, str]:
    return (drug_id_a, drug_id_b) if drug_id_a <= drug_id_b else (drug_id_b, drug_id_a)


def build_index(xml_path: Path, index_path: Path) -> dict[str, str]:
    """Stream the DrugBank XML once into a SQLite pair index (atomic: temp file + rename).

    The index holds case-folded name/synonym keys -> DrugBank ids and one row per unordered
    id pair with the source's description and severity element (absent in this export).
    """
    xml_path = Path(xml_path)
    index_path = Path(index_path)
    if not xml_path.exists():
        raise FileNotFoundError(f"DrugBank XML not found at {xml_path}")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_name(index_path.name + ".tmp")
    if tmp.exists():
        tmp.unlink()

    stat = xml_path.stat()
    meta = {
        "source_file": xml_path.name,
        "source_size": str(stat.st_size),
        "source_mtime": str(int(stat.st_mtime)),
        "version": "",
        "exported_on": "",
        "built_at": datetime.now(UTC).isoformat(),
    }
    drugs = aliases = pairs = 0

    db = sqlite3.connect(tmp)
    try:
        db.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE aliases (key TEXT PRIMARY KEY, drug_id TEXT NOT NULL);
            CREATE TABLE pairs (
                a TEXT NOT NULL, b TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (a, b)
            );
            """
        )
        with xml_path.open("rb") as f:
            for _event, elem in ET.iterparse(f, events=("end",)):
                if elem.tag == _NS + "drugbank":
                    meta["version"] = (elem.get("version") or "").strip()
                    meta["exported_on"] = (elem.get("exported-on") or "").strip()
                elif elem.tag == _NS + "drug":
                    # Only top-level records (they carry a type attribute) may contribute
                    # names or pairs. The <drug> references nested in <pathways>/<drugs>
                    # repeat other drugs' ids and must not compete for an alias key.
                    if elem.get("type") is None:
                        elem.clear()
                        continue
                    ids = [
                        (el.text or "").strip()
                        for el in elem.findall(f"{_NS}drugbank-id")
                        if (el.text or "").strip()
                    ]
                    if not ids:
                        elem.clear()
                        continue
                    primary = next(
                        (
                            el.text.strip()
                            for el in elem.findall(f"{_NS}drugbank-id")
                            if el.get("primary") == "true" and (el.text or "").strip()
                        ),
                        ids[0],
                    )
                    name_el = elem.find(f"{_NS}name")
                    if name_el is None or not (name_el.text or "").strip():
                        elem.clear()
                        continue
                    db.executemany(
                        "INSERT OR IGNORE INTO aliases VALUES (?, ?)",
                        [(_key(name_el.text), primary)],
                    )
                    synonyms = [
                        (_key(el.text), primary)
                        for el in elem.findall(f"{_NS}synonyms/{_NS}synonym")
                        if (el.text or "").strip()
                    ]
                    if synonyms:
                        db.executemany("INSERT OR IGNORE INTO aliases VALUES (?, ?)", synonyms)
                    rows = []
                    for it in elem.findall(f"{_NS}drug-interactions/{_NS}drug-interaction"):
                        partner = (it.findtext(f"{_NS}drugbank-id") or "").strip()
                        if not partner or partner == primary:
                            continue
                        a, b = _pair_id(primary, partner)
                        rows.append(
                            (
                                a,
                                b,
                                (it.findtext(f"{_NS}description") or "").strip(),
                                (it.findtext(f"{_NS}severity") or "").strip(),
                            )
                        )
                    if rows:
                        db.executemany(
                            "INSERT OR IGNORE INTO pairs VALUES (?, ?, ?, ?)", rows
                        )
                        pairs += len(rows)
                    drugs += 1
                    elem.clear()
                    if drugs % 500 == 0:
                        db.commit()
        meta["drugs"] = str(drugs)
        meta["aliases"] = str(db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0])
        meta["pairs"] = str(db.execute("SELECT COUNT(*) FROM pairs").fetchone()[0])
        db.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", meta.items())
        db.commit()
    except BaseException:
        db.close()
        tmp.unlink(missing_ok=True)
        raise
    db.close()
    os.replace(tmp, index_path)
    logger.info(
        "DrugBank index built: %s drugs, %s pairs -> %s", meta["drugs"], meta["pairs"], index_path
    )
    return meta


class SourceUnavailable(RuntimeError):
    """The DrugBank XML/index cannot be used for lookups."""


class DrugBankDDIProvider:
    """DrugBank pair lookup over the prebuilt SQLite index; builds it from the XML once.

    Never raises from lookup_pair: every failure (missing file, malformed index, unknown
    drug, lookup error) is a CANNOT_ASSESS result, so a broken source cannot fail an
    evaluation. Lookups are safe from FastAPI's thread pool (one shared connection guarded
    by a lock).
    """

    def __init__(
        self,
        xml_path: Path | str | None = None,
        index_path: Path | str | None = None,
        *,
        build_if_missing: bool = True,
    ) -> None:
        self._xml = Path(xml_path) if xml_path else config.DRUGBANK_XML_PATH
        self._index = Path(index_path) if index_path else config.DDI_INDEX_PATH
        self._build_if_missing = build_if_missing
        self._db: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def ensure_index(self) -> None:
        """Open the index, building it from the XML when missing or stale. Raises on failure."""
        if self._db is not None:
            return
        if not self._index.exists() or not self._source_is_current():
            if not self._xml.exists():
                raise SourceUnavailable(f"DrugBank XML not found at {self._xml}")
            if not self._build_if_missing:
                raise SourceUnavailable(f"DrugBank index not found at {self._index}")
            logger.info(
                "Building DrugBank DDI index at %s from %s (one-time; takes minutes)...",
                self._index,
                self._xml,
            )
            build_index(self._xml, self._index)
        db = sqlite3.connect(self._index, check_same_thread=False)
        db.execute("SELECT 1 FROM meta").fetchone()
        self._db = db

    def meta(self) -> dict[str, str]:
        self.ensure_index()
        assert self._db is not None
        with self._lock:
            return dict(self._db.execute("SELECT key, value FROM meta"))

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    def __enter__(self):
        self.ensure_index()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _source_is_current(self) -> bool:
        """True when the built index was made from the XML file as it is now."""
        try:
            db = sqlite3.connect(self._index)
            try:
                meta = dict(db.execute("SELECT key, value FROM meta"))
            finally:
                db.close()
            stat = self._xml.stat()
            return meta.get("source_size") == str(stat.st_size) and meta.get(
                "source_mtime"
            ) == str(int(stat.st_mtime))
        except (sqlite3.Error, OSError):
            return False

    def lookup_pair(self, drug_a: str, drug_b: str) -> DDIResult:
        try:
            self.ensure_index()
            version = self._version()
            key_a, key_b = _key(drug_a), _key(drug_b)
            with self._lock:
                assert self._db is not None
                id_a = self._drug_id(key_a)
                id_b = self._drug_id(key_b)
                if id_a is None or id_b is None:
                    missing = drug_a if id_a is None else drug_b
                    return _cannot_assess(
                        drug_a,
                        drug_b,
                        f"'{missing}' was not found in the DrugBank index.",
                        version,
                    )
                if id_a == id_b:
                    return _cannot_assess(
                        drug_a, drug_b, "Both entries name the same drug; no pair to check.", version
                    )
                a, b = _pair_id(id_a, id_b)
                row = self._db.execute(
                    "SELECT description, severity FROM pairs WHERE a = ? AND b = ?", (a, b)
                ).fetchone()
            if row is not None:
                desc = row[0] or None
                return DDIResult(
                    type="DDI",
                    drug_a=drug_a,
                    drug_b=drug_b,
                    status=DDIStatus.INTERACTION_FOUND,
                    # Only a structured severity the source states is used; this export has
                    # none, so the result stays "unknown" — never inferred from wording.
                    severity=row[1] or "unknown",
                    mechanism=desc,
                    explanation=desc,
                    action="Review the reported interaction with the pharmacist before the drugs are co-administered.",
                    description=desc,
                    source_version=version,
                    evidence=desc,
                    needs_review=True,
                )
            return DDIResult(
                type="DDI",
                drug_a=drug_a,
                drug_b=drug_b,
                status=DDIStatus.NO_INTERACTION_REPORTED_BY_SOURCE,
                explanation=f"{SOURCE_NAME} reports no interaction between {drug_a} and {drug_b}.",
                source_version=version,
                needs_review=False,
            )
        except Exception as exc:  # noqa: BLE001 - a broken source must never fail an evaluation
            logger.exception("DrugBank lookup failed for %s + %s", drug_a, drug_b)
            return _cannot_assess(
                drug_a, drug_b, f"DrugBank lookup unavailable ({type(exc).__name__}).", None
            )

    def _drug_id(self, key: str) -> str | None:
        assert self._db is not None
        row = self._db.execute("SELECT drug_id FROM aliases WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _version(self) -> str | None:
        assert self._db is not None
        with self._lock:
            meta = dict(self._db.execute("SELECT key, value FROM meta"))
        version, exported = meta.get("version", ""), meta.get("exported_on", "")
        if not version and not exported:
            return None
        return f"{version or '?'}" + (f" (exported {exported})" if exported else "")


def _cannot_assess(a: str | None, b: str | None, reason: str, version: str | None) -> DDIResult:
    return DDIResult(
        type="DDI",
        drug_a=a,
        drug_b=b,
        status=DDIStatus.CANNOT_ASSESS,
        reason=reason,
        explanation=f"Drug–drug interaction check could not assess {a} + {b}. {reason}".strip() if (a and b) else reason,
        action="Confirm the drug identity, or review the drug's interactions manually; DrugBank could not answer this pair.",
        source_version=version,
        needs_review=True,
    )


def _evidence(result: DDIResult) -> tuple[Evidence, ...]:
    title = f"{SOURCE_NAME} drug–drug interaction"
    if result.source_version:
        title += f" ({result.source_version})"
    return (
        Evidence(
            source_id=f"drugbank:{result.drug_a}+{result.drug_b}",
            title=title,
            quote=result.description,
            provenance=DataProvenance.PUBLIC,
        ),
    )


def _finding(result: DDIResult, rule_id: str, order_id: str | None = None) -> Finding:
    a, b = result.drug_a, result.drug_b
    if result.status is DDIStatus.INTERACTION_FOUND:
        message = f"{SOURCE_NAME} reports an interaction between {a} and {b}."
        if result.description:
            message += f" {_truncate(result.description)}"
        if result.severity == "unknown":
            message += " The source gives no severity classification for this pair."
        return Finding(
            rule_id=rule_id,
            outcome=Outcome.FLAG,
            severity=_FINDING_SEVERITY.get(result.severity, Severity.MODERATE),
            order_id=order_id,
            message=message,
            evidence=_evidence(result),
        )
    if result.status is DDIStatus.NO_INTERACTION_REPORTED_BY_SOURCE:
        return Finding(
            rule_id=rule_id,
            outcome=Outcome.PASS,
            severity=Severity.INFO,
            order_id=order_id,
            message=(
                f"{SOURCE_NAME} reports no interaction between {a} and {b}. This means only "
                "that the source does not report one, not that the pair is guaranteed safe."
            ),
            evidence=_evidence(result),
        )
    return Finding(
        rule_id=rule_id,
        outcome=Outcome.CANNOT_ASSESS,
        severity=Severity.HIGH,
        order_id=order_id,
        message=(
            f"Drug–drug interaction check could not assess {a} + {b}. {result.reason or ''}"
        ).strip(),
    )


def _order_reason(order: DrugOrder) -> str:
    if order.norm_status is NormStatus.AMBIGUOUS:
        return f"'{order.raw_text}' matches more than one drug and was not confirmed"
    return f"'{order.raw_text}' matches no known drug"


def check_pairs(episode: Episode, provider: DDIProvider) -> PairChecks:
    """Check every unique unordered pair of the episode's identified medications.

    Medication identity is only what the existing catalog already produced (order.generic);
    nothing is re-normalised or guessed. Fewer than two medications means no pairs. A drug
    that was not identified contributes a CANNOT_ASSESS finding instead of a pair, and a
    provider that raises is caught per pair and flags the checks as crashed.
    """
    identified: dict[str, str] = {}  # catalog key -> canonical generic, in episode order
    unidentified: list[DrugOrder] = []
    for order in episode.orders:
        if is_identified(order) and order.generic:
            identified.setdefault(_key(order.generic), order.generic)
        else:
            unidentified.append(order)

    if len(identified) + len(unidentified) < 2:
        return PairChecks((), False)

    findings: list[DDIFinding] = []
    crashed = False
    for drug_a, drug_b in itertools.combinations(identified.values(), 2):
        a, b = sorted((drug_a, drug_b))
        try:
            result = provider.lookup_pair(a, b)
        except Exception as exc:  # noqa: BLE001 - defensive; providers are meant not to raise
            logger.exception("DDI provider failed for %s + %s", a, b)
            crashed = True
            result = _cannot_assess(
                a, b, f"Check failed ({type(exc).__name__}); result not available.", None
            )
        base = {
            DDIStatus.INTERACTION_FOUND: DDI_INTERACTION,
            DDIStatus.NO_INTERACTION_REPORTED_BY_SOURCE: DDI_NO_INTERACTION,
            DDIStatus.CANNOT_ASSESS: DDI_CANNOT_ASSESS,
        }[result.status]
        findings.append(DDIFinding(_finding(result, f"{base}:{a}+{b}"), result))

    for order in unidentified:
        reason = _order_reason(order)
        result = DDIResult(
            type="DDI",
            drug_a=order.raw_text,
            status=DDIStatus.CANNOT_ASSESS,
            reason=(
                f"{reason}, so its interactions with the other medication(s) in this episode "
                "cannot be checked."
            ),
            explanation=(
                f"Drug–drug interaction check could not assess '{order.raw_text}': {reason}."
            ),
            action="Confirm the drug identity, or review the drug's interactions manually.",
            source=SOURCE_NAME,
            needs_review=True,
        )
        findings.append(
            DDIFinding(
                _finding(result, f"{DDI_CANNOT_ASSESS}:order:{order.id}", order_id=order.id),
                result,
            )
        )
    return PairChecks(tuple(findings), crashed)
