"""Questions about a finished evaluation, answered by a language model from that evaluation only.

Like the summary (summary.py) this is explanation only: it runs after evaluate_episode() has
decided every outcome, sees the same de-identified input (rule results, actions and guideline
evidence), and nothing it returns is stored in or changes the report. Each answer goes through
the summary's grounding checks (no invented number, dose, drug, source or action, never "safe")
and is withheld when it fails one.

Provider calls are kept few, so a free-tier key lasts a demo:
- nothing is called until a question is asked, and one question is one call;
- a repeated question (same words, same conversation) is answered from a cache;
- each evaluation may reach the provider at most config.CHAT_MAX_QUESTIONS times;
- only the last few turns of the conversation are sent, each truncated.
Without a configured provider no call is ever made and the answer says so.
"""

import json
import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Literal, Protocol

import httpx
from pydantic import BaseModel, Field

from . import config
from .summary import (
    _DRUG_CLASSES,
    _THINK,
    AI_WORDED,
    RULE_BASED,
    ProviderError,
    antibiotic_names,
    evidence_for,
    grounding_problem,
    provider_from_env,
    summary_input,
)

if TYPE_CHECKING:
    from .service import EvaluationReport

logger = logging.getLogger(__name__)

NOTICE = (
    "Explanatory only. Answers restate this evaluation's rule results and evidence; they do not "
    "change the result. The pharmacist reviews every finding."
)
OUT_OF_SCOPE = "This evaluation does not cover that."
WITHHELD = (
    "I can't answer that from this evaluation without going beyond its findings. The findings "
    "above are the result; please check anything else with the stewardship team."
)
UNAVAILABLE = (
    "Questions need a language model, and none is configured (HC03_LLM_*). The findings and "
    "summary above are the full result."
)

SYSTEM_PROMPT = (
    "You answer a pharmacist's questions about one antibiotic stewardship evaluation, given as "
    "JSON. The rule results were decided by a deterministic engine and are final; you only "
    "explain them. Answer in at most 120 words, plain text, no markdown.\n"
    "Rules:\n"
    "1. Use only facts in the evaluation JSON. Do not name any drug, drug class, dose, duration, "
    "frequency, number or guideline that is not in it.\n"
    "2. Do not change, soften or re-judge any outcome or severity. A CANNOT_ASSESS check "
    "'cannot be assessed'; name its missing inputs.\n"
    "3. Never call the prescription safe, appropriate or free of issues.\n"
    "4. Do not give advice of your own. When asked what to do, quote the recommended_action of "
    "the relevant findings.\n"
    "5. When asked why, explain from the finding's message and cite its sources.\n"
    f"6. If the evaluation does not answer the question, reply exactly: {OUT_OF_SCOPE}"
)

HISTORY_TURNS = 6
TURN_CHARS = 600


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class ChatAnswer(BaseModel):
    answer: str
    generated_by: Literal["AI_WORDED", "RULE_BASED"]
    model: str | None = None
    # Why model text was not shown. A fixed phrase, never the provider's error text.
    fallback_reason: str | None = None
    # True when the answer came from the cache and no provider call was made.
    cached: bool = False
    # Provider calls this evaluation has left, or None when no provider is configured.
    questions_left: int | None = None
    notice: str = NOTICE


class ChatLimitError(Exception):
    """An evaluation has used its provider calls."""


class Answerer(Protocol):
    calls_provider: bool

    def answer(
        self, data: dict, payload: str, question: str, history: Sequence[ChatTurn]
    ) -> ChatAnswer: ...


class UnavailableAnswerer:
    """No provider configured: says so, and never makes a call."""

    calls_provider = False

    def answer(self, data, payload, question, history) -> ChatAnswer:
        return ChatAnswer(
            answer=UNAVAILABLE,
            generated_by=RULE_BASED,
            fallback_reason="no language model configured",
        )


def chat_prompt(payload: str, question: str, history: Sequence[ChatTurn]) -> str:
    """The user message: the evaluation, the last few turns, then the question."""
    lines = [f"Evaluation:\n{payload}"]
    recent = list(history)[-HISTORY_TURNS:]
    if recent:
        lines.append("Conversation so far:")
        lines += [f"{t.role}: {t.content[:TURN_CHARS]}" for t in recent]
    lines.append(f"Question: {question}")
    return "\n\n".join(lines)


class LlmAnswerer:
    """Answers worded by a language model and checked like the summary; withheld on failure."""

    calls_provider = True
    MAX_CHARS = 1200

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

    def answer(
        self, data: dict, payload: str, question: str, history: Sequence[ChatTurn]
    ) -> ChatAnswer:
        try:
            text = self._complete(SYSTEM_PROMPT, chat_prompt(payload, question, history))
            text = _THINK.sub("", text or "").strip()
        except ProviderError as exc:
            reason = exc.reason
        except httpx.TimeoutException:
            reason = "provider timeout"
        except Exception as exc:  # any other failure: record its type only, never its text
            reason = f"provider error ({type(exc).__name__})"
        else:
            reason = self._problem(text, payload, data, question)
            if reason is None:
                return ChatAnswer(answer=text, generated_by=AI_WORDED, model=self._model)
        logger.warning("Chat answer not used (%s)", reason)
        return ChatAnswer(
            answer=WITHHELD, generated_by=RULE_BASED, model=self._model, fallback_reason=reason
        )

    def _problem(self, text: str, payload: str, data: dict, question: str) -> str | None:
        if not text:
            return "empty response"
        if len(text) > self.MAX_CHARS:
            return "response too long"
        if text == OUT_OF_SCOPE:
            return None
        # The answer may name a drug the question asked about ("X is not in this evaluation"),
        # but no number, dose or action from the question.
        return grounding_problem(text, payload, data, self._known_drugs, named_drugs=question)


class EvaluationChat:
    """Answers questions about stored evaluations, with a cache and a per-evaluation call cap."""

    def __init__(self, answerer: Answerer, *, max_questions: int | None = None) -> None:
        self.answerer = answerer
        self.max_questions = config.CHAT_MAX_QUESTIONS if max_questions is None else max_questions
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, str], ChatAnswer] = {}
        self._calls: dict[str, int] = {}

    def ask(self, report: "EvaluationReport", request: ChatRequest) -> ChatAnswer:
        question = " ".join(request.question.split())
        recent = request.history[-HISTORY_TURNS:]
        key = (
            report.id,
            json.dumps([question.lower(), [t.model_dump() for t in recent]], ensure_ascii=False),
        )
        with self._lock:
            if key in self._cache:
                return self._cache[key].model_copy(
                    update={"cached": True, "questions_left": self._left(report.id)}
                )
            if self.answerer.calls_provider:
                if self._calls.get(report.id, 0) >= self.max_questions:
                    raise ChatLimitError(
                        f"This evaluation has used its {self.max_questions} questions."
                    )
                self._calls[report.id] = self._calls.get(report.id, 0) + 1

        data = summary_input(report, evidence_for(report))
        payload = json.dumps(data, ensure_ascii=False, indent=1)
        answer = self.answerer.answer(data, payload, question, recent)

        with self._lock:
            answer = answer.model_copy(update={"questions_left": self._left(report.id)})
            # A provider failure may pass on retry, so only a real answer or a check failure
            # (the same text again at temperature 0) is kept.
            if not (answer.fallback_reason or "").startswith("provider"):
                self._cache[key] = answer
        return answer

    def _left(self, evaluation_id: str) -> int | None:
        if not self.answerer.calls_provider:
            return None
        return max(0, self.max_questions - self._calls.get(evaluation_id, 0))


def answerer_from_env() -> Answerer:
    """LlmAnswerer on the HC03_LLM_* provider, or one that makes no call when none is set."""
    complete = provider_from_env()
    if complete is None:
        return UnavailableAnswerer()
    return LlmAnswerer(complete, model=complete.model, known_drugs=antibiotic_names())
