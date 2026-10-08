"""Plain-language summary of a finished evaluation, optionally worded by a language model.

The summary is explanation only. It is written after evaluate_episode() has produced every
outcome and severity, from a copy of those results and the guideline passages already retrieved
for them, and it is stored beside the report, never in it: nothing here can change PASS, FLAG or
CANNOT_ASSESS, a severity, an action or the review rules.

The model sees only the structured results and the evidence (no patient identifiers, no episode
or evaluation ids, no raw episode). Its text is checked before use and replaced by the
deterministic summary when the provider fails or the text fails a check:

- it must not be empty or too long;
- it must say "cannot be assessed" when any check could not be assessed, and must not call the
  prescription safe or free of issues while a check is flagged or unassessed;
- every number it states must appear in the input, and it must not state a dose, duration or
  dosing frequency in words that the input does not contain;
- every antibiotic or antibiotic class it names must appear in the input;
- every guideline body it cites must appear in the input;
- every action it recommends (switch, stop, start, culture...) must be one the rules recommended.

The provider is any OpenAI-compatible chat-completions endpoint: Groq and Gemini have presets,
anything else (OpenAI, Ollama, vLLM) is set by base URL. It is configured with HC03_LLM_*
environment variables and is off unless configured; the API key is only ever sent in the
Authorization header and is never logged or returned.
"""

import csv
import json
import logging
import re
import time
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Literal, Protocol

import httpx
from pydantic import BaseModel

from . import config
from .evidence import Passage
from .schemas import Outcome

if TYPE_CHECKING:
    from .service import EvaluationReport

logger = logging.getLogger(__name__)

NOTICE = (
    "Explanatory only. This summary restates the rule results below; it does not determine the "
    "clinical result. The deterministic findings are the decision and the pharmacist reviews each."
)
RULE_BASED, AI_WORDED = "RULE_BASED", "AI_WORDED"

# Hosted OpenAI-compatible endpoints. Any other endpoint is set with HC03_LLM_BASE_URL.
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1", "qwen/qwen3.8-27b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash"),
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THINK = re.compile(r"<think>.*?</think>", re.S)
_CANNOT_ASSESS = ("cannot be assessed", "cannot_assess", "could not be assessed")
# Calling a prescription safe is a clinical judgement the rules never make.
_SAFE = re.compile(r"\bsafe\b")
# Reassurance that would contradict a FLAG or a CANNOT_ASSESS.
_REASSURANCE = re.compile(
    r"\b(?:no (?:issues?|concerns?|problems?)|fully assessed|all checks passed|"
    r"nothing (?:to|needs to be) (?:review|change)\w*)\b"
)
_WORD_NUMBER = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|twenty|thirty)"
)
_WORDED_AMOUNT = re.compile(
    rf"\b{_WORD_NUMBER}[ -](?:days?|weeks?|months?|hours?|doses?|grams?|g|mg|tablets?|capsules?)\b"
)
_FREQUENCY = re.compile(
    r"\b(?:once|twice|thrice|daily|weekly|hourly|bd|bid|tds|tid|qid|qds|od|q\d+h)\b"
)
# Guideline bodies and drug references a model might cite from memory. Acronyms match in
# upper case only ("WHO", not "who").
_SOURCE_ACRONYMS = re.compile(
    r"\b(?:IDSA|NICE|CDC|ICMR|WHO|NCDC|EUCAST|CLSI|BNF|ATS|BTS|ESCMID|FDA|EMA|AIIMS|SHEA|ERS)\b"
)
_SOURCE_NAMES = re.compile(
    r"\b(?:sanford|uptodate|cochrane|british national formulary|harrison'?s|medscape|lexicomp)\b"
)
_DRUG_CLASSES = (
    "aminoglycoside", "carbapenem", "cephalosporin", "fluoroquinolone", "quinolone",
    "glycopeptide", "lincosamide", "macrolide", "monobactam", "nitroimidazole", "oxazolidinone",
    "penicillin", "polymyxin", "sulfonamide", "tetracycline", "beta-lactam", "rifamycin",
)  # fmt: skip
# Recommendation verbs, and the rule suggestion that permits each. A verb is also allowed when
# the input itself uses it (for example "Review" in an action text).
_RECOMMENDATIONS = {
    "switch": ("switch",), "change to": ("switch",), "replace": ("switch",),
    "substitute": ("switch",), "step down": ("switch",), "de-escalate": ("switch",),
    "escalate": (), "stop": ("stop",), "discontinue": ("stop",), "start": (), "initiate": (),
    "add": (), "prescribe": (), "administer": (), "give": (), "continue": (),
    "increase": ("adjust_dose",), "decrease": ("adjust_dose",), "reduce": ("adjust_dose",),
    "extend": ("adjust_duration",), "shorten": ("adjust_duration",),
    "send": ("send_culture",), "obtain": ("send_culture",), "collect": ("send_culture",),
    "repeat": (),
}  # fmt: skip


# What each rule checks, from the rule docstrings in rules.py and culture.py, so the model
# names a check instead of guessing from its id.
CHECK_NAMES = {
    "R0_IDENTIFIED": "drug identity",
    "R1_INDICATION": "guideline indication",
    "R2_AWARE": "WHO AWaRe tier",
    "R3_DOSE": "dose",
    "R4_RENAL": "kidney-function dosing",
    "R5_DURATION": "duration",
    "R6_ALLERGY": "allergy",
    "C1_CULTURE_BEFORE_WATCH": "culture before Watch/Reserve therapy",
    "C3_BUG_DRUG_MISMATCH": "organism resistance to the drug",
    "C4_DE_ESCALATE": "step-down option from the culture",
    "C5_NO_GROWTH": "no-growth culture review",
    "C6_CONTAMINANT": "probable contaminant",
    "C7_INTERMEDIATE": "intermediate susceptibility",
    "C8_NOT_TESTED": "drug not in the susceptibility panel",
    "C9_ORGANISM_UNKNOWN": "organism not in the reference list",
}


def _check_name(rule_id: str) -> str:
    """DDI rule ids carry the pair ("DDI_INTERACTION:a+b"), so they are named by prefix."""
    if rule_id.startswith("DDI_"):
        return "drug–drug interaction"
    return CHECK_NAMES.get(rule_id, rule_id)


def _check(item) -> str:
    name = _check_name(item.rule_id)
    return f"{item.rule_id} {name}" + (f" ({item.drug})" if item.drug else "")


class EvaluationSummary(BaseModel):
    text: str
    generated_by: Literal["AI_WORDED", "RULE_BASED"]
    model: str | None = None
    # Why model text was not used, when a model was tried. A fixed phrase, never the provider's
    # error text, so no URL, header or key can reach the response.
    fallback_reason: str | None = None
    sources: tuple[str, ...] = ()
    notice: str = NOTICE


class Summarizer(Protocol):
    def explain(
        self, evaluation: "EvaluationReport", evidence: Sequence[Passage]
    ) -> EvaluationSummary: ...


def evidence_for(evaluation: "EvaluationReport") -> list[Passage]:
    """The guideline passages already retrieved for the report's findings, without repeats."""
    seen: dict[tuple[str, str], Passage] = {}
    for item in evaluation.items:
        for p in item.guideline_passages:
            seen.setdefault((p.citation, p.text), p)
    return list(seen.values())


def _sources(evaluation: "EvaluationReport", evidence: Sequence[Passage]) -> tuple[str, ...]:
    out: list[str] = []
    for item in evaluation.items:
        if item.outcome is Outcome.PASS:
            continue
        for e in item.evidence:
            out.append(e.title + (f", {e.page}" if e.page else ""))
    out += [p.citation for p in evidence]
    return tuple(dict.fromkeys(out))


class TemplateSummarizer:
    """Deterministic summary: the status, then each non-pass finding's existing explanation and
    action from advice.py and evidence.py."""

    def explain(
        self, evaluation: "EvaluationReport", evidence: Sequence[Passage]
    ) -> EvaluationSummary:
        flagged = [i for i in evaluation.items if i.outcome is Outcome.FLAG]
        unassessed = [i for i in evaluation.items if i.outcome is Outcome.CANNOT_ASSESS]
        lines = [
            f"Evaluation status {evaluation.status.value}: {len(flagged)} finding(s) flagged, "
            f"{len(unassessed)} check(s) cannot be assessed."
        ]
        for item in flagged + unassessed:
            if item.rule_id.startswith("DDI_"):
                subject = f"Drug–drug interaction ({item.drug})"
            else:
                subject = f"{item.rule_id} ({item.drug})" if item.drug else item.rule_id
            line = f"- {subject}, {item.outcome.value} {item.severity}: {item.explanation}"
            if item.action:
                line += f" Action: {item.action}"
            lines.append(line)
        if evaluation.culture.state == "NOT_AVAILABLE" or evaluation.culture.action:
            culture = f"Culture: {evaluation.culture.message}"
            if evaluation.culture.action:
                culture += f" {evaluation.culture.action}"
            lines.append(culture)
        return EvaluationSummary(
            text="\n".join(lines),
            generated_by=RULE_BASED,
            sources=_sources(evaluation, evidence),
        )


def summary_input(evaluation: "EvaluationReport", evidence: Sequence[Passage]) -> dict:
    """Everything the model is allowed to see: rule results, actions and guideline evidence.

    No patient, episode or evaluation identifier, no demographics and no ruleset hash."""
    return {
        "status": evaluation.status.value,
        "syndrome": evaluation.syndrome.name,
        "culture": evaluation.culture.model_dump(),
        "warnings": list(evaluation.warnings),
        "findings": [
            {
                "rule_id": i.rule_id,
                "check": _check_name(i.rule_id),
                "outcome": i.outcome.value,
                "severity": i.severity,
                "drug": i.drug,
                "message": i.message,
                "recommended_action": i.action,
                "suggested_action": i.suggestion_action,
                "missing_inputs": list(i.missing_inputs),
                "sources": [e.title + (f", {e.page}" if e.page else "") for e in i.evidence],
            }
            for i in evaluation.items
            if i.outcome is not Outcome.PASS
        ],
        "passed_checks": [_check(i) for i in evaluation.items if i.outcome is Outcome.PASS],
        "guideline_evidence": [{"citation": p.citation, "text": p.text} for p in evidence],
    }


SYSTEM_PROMPT = (
    "You summarise an antibiotic stewardship evaluation for a pharmacist in at most 150 words. "
    "The rule results in the input are final and were decided by a deterministic engine; you "
    "only explain them. Cover, in this order: what was checked (passed_checks and findings), the "
    "issues flagged, any information that is missing, the recommended_action of each finding, "
    "and the sources that support them.\n"
    "Rules:\n"
    "1. Do not change, soften or re-judge any outcome or severity; restate them.\n"
    "2. For every FLAG explain why it was raised and state its recommended_action.\n"
    "3. For every CANNOT_ASSESS finding write 'cannot be assessed' and name the missing input. "
    "Never call the prescription safe, appropriate or free of issues.\n"
    "4. Use only facts in the input. Do not name any drug, drug class, dose, duration, frequency "
    "or number that is not in the input, and do not add advice or actions of your own.\n"
    "5. Cite only the sources and citations given in the input.\n"
    "Return plain text only, no markdown."
)


class ProviderError(Exception):
    """A provider call failed. `reason` is a fixed, secret-free phrase for the response."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LlmSummarizer:
    """Summary worded by a language model, checked, with the deterministic summary as fallback.

    `complete(system, user)` is any text-in/text-out call (see OpenAICompatibleProvider). It
    receives strings only, so it has no handle on the report.
    """

    MAX_CHARS = 2000

    def __init__(
        self,
        complete: Callable[[str, str], str],
        *,
        model: str | None = None,
        known_drugs: Iterable[str] = (),
    ) -> None:
        self._complete = complete
        self._model = model
        self._known_drugs = frozenset(d.lower() for d in known_drugs) | frozenset(_DRUG_CLASSES)
        self._fallback = TemplateSummarizer()

    def explain(
        self, evaluation: "EvaluationReport", evidence: Sequence[Passage]
    ) -> EvaluationSummary:
        data = summary_input(evaluation, evidence)
        payload = json.dumps(data, ensure_ascii=False, indent=1)
        started = time.monotonic()
        try:
            text = _THINK.sub("", self._complete(SYSTEM_PROMPT, payload) or "").strip()
        except ProviderError as exc:
            reason = exc.reason
        except httpx.TimeoutException:
            reason = "provider timeout"
        except Exception as exc:  # any other failure: record its type only, never its text
            reason = f"provider error ({type(exc).__name__})"
        else:
            reason = self._problem(text, payload, data)
            if reason is None:
                logger.info(
                    "LLM summary accepted (model %s, %.1f s)",
                    self._model,
                    time.monotonic() - started,
                )
                return EvaluationSummary(
                    text=text,
                    generated_by=AI_WORDED,
                    model=self._model,
                    sources=_sources(evaluation, evidence),
                )
        logger.warning("LLM summary not used (%s); showing the rule-based summary", reason)
        summary = self._fallback.explain(evaluation, evidence)
        return summary.model_copy(update={"fallback_reason": reason, "model": self._model})

    def _problem(self, text: str, payload: str, data: dict) -> str | None:
        """Why the model's text cannot be shown, or None if it passes every check."""
        if not text:
            return "empty response"
        if len(text) > self.MAX_CHARS:
            return "response too long"
        lower, source = text.lower(), payload.lower()
        outcomes = {f["outcome"] for f in data["findings"]}
        if "CANNOT_ASSESS" in outcomes and not any(p in lower for p in _CANNOT_ASSESS):
            return "did not state that a check cannot be assessed"
        if _SAFE.search(lower):
            return "calls the prescription safe"
        if outcomes and (m := _REASSURANCE.search(lower)):
            return f"contradicts a flagged or unassessed check: '{m.group()}'"
        allowed = set(_NUMBER.findall(payload))
        invented = [n for n in _NUMBER.findall(text) if n not in allowed]
        if invented:
            return f"number not in the evaluation: {invented[0]}"
        for m in (*_WORDED_AMOUNT.finditer(lower), *_FREQUENCY.finditer(lower)):
            if not re.search(rf"\b{re.escape(m.group())}\b", source):
                return f"dose, duration or frequency not in the evaluation: '{m.group()}'"
        for drug in sorted(self._known_drugs):
            if drug not in source and re.search(rf"\b{re.escape(drug)}s?\b", lower):
                return f"drug not in the evaluation: {drug}"
        for m in (*_SOURCE_ACRONYMS.finditer(text), *_SOURCE_NAMES.finditer(lower)):
            if m.group().lower() not in source:
                return f"source not in the evaluation: {m.group()}"
        suggested = {f["suggested_action"] for f in data["findings"]}
        for verb, permitted_by in _RECOMMENDATIONS.items():
            if not re.search(rf"\b{re.escape(verb)}\b", lower):
                continue
            if re.search(rf"\b{re.escape(verb)}\b", source) or suggested & set(permitted_by):
                continue
            return f"recommendation not in the evaluation: '{verb}'"
        return None


class OpenAICompatibleProvider:
    """POST {base_url}/chat/completions, the API shared by Groq, Gemini, OpenAI, Ollama and vLLM.

    Errors are raised as ProviderError with a fixed reason; the key, URL and response body are
    never put in an exception message."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout_s: float = 20.0,
        max_tokens: int = 700,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._max_tokens = max_tokens
        self._client = client or httpx.Client(timeout=timeout_s)

    def __repr__(self) -> str:
        return f"OpenAICompatibleProvider(model={self.model!r})"

    def __call__(self, system: str, user: str) -> str:
        try:
            response = self._client.post(
                self._url,
                headers=self._headers,
                json={
                    "model": self.model,
                    "temperature": 0,
                    "max_tokens": self._max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        except httpx.TimeoutException:
            raise ProviderError("provider timeout") from None
        except httpx.HTTPError as exc:
            raise ProviderError(f"provider unreachable ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise ProviderError(f"provider HTTP {response.status_code}")
        try:
            return response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("provider response not readable") from None


def antibiotic_names() -> frozenset[str]:
    """Antibiotic generics (and their components), aliases and Indian brands from the catalog
    data, used to catch a drug the model brought in itself."""
    names: set[str] = set()
    for path, columns in (
        (config.AWARE_CSV, ("generic",)),
        (config.DATA_DIR / "drug_aliases.csv", ("alias", "generic")),
        (config.DATA_DIR / "brands_india.csv", ("brand",)),
    ):
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for column in columns:
                    value = (row.get(column) or "").strip().lower()
                    names |= {value, *(p.strip() for p in value.split("/"))} - {""}
    return frozenset(n for n in names if len(n) > 3)


def summarizer_from_env() -> Summarizer:
    """LlmSummarizer when a provider is fully configured by HC03_LLM_*, else the template.

    HC03_LLM_PROVIDER=groq|gemini fills in the base URL and a default model; a hosted provider
    without HC03_LLM_API_KEY stays off. Without a provider, HC03_LLM_BASE_URL and HC03_LLM_MODEL
    select any OpenAI-compatible endpoint (a local one needs no key). Nothing configured means no
    API call is ever made.
    """
    provider = (config.LLM_PROVIDER or "").lower() or None
    if provider and provider not in PROVIDERS:
        logger.warning("Unknown HC03_LLM_PROVIDER %r; using the rule-based summary", provider)
        return TemplateSummarizer()
    preset_url, preset_model = PROVIDERS.get(provider, (None, None))
    base_url = config.LLM_BASE_URL or preset_url
    model = config.LLM_MODEL or preset_model
    if not (base_url and model):
        return TemplateSummarizer()
    if provider and not config.LLM_API_KEY:
        logger.warning(
            "HC03_LLM_PROVIDER=%s has no API key; using the rule-based summary", provider
        )
        return TemplateSummarizer()
    complete = OpenAICompatibleProvider(
        base_url, model, api_key=config.LLM_API_KEY, timeout_s=config.LLM_TIMEOUT_S
    )
    return LlmSummarizer(complete, model=model, known_drugs=antibiotic_names())
