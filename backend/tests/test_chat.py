"""Questions about an evaluation are answered from that evaluation only, cost few provider calls,
and can never change the result."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.stewardship.api import create_app
from backend.stewardship.audit import JsonlAuditLog
from backend.stewardship.chat import (
    OUT_OF_SCOPE,
    UNAVAILABLE,
    WITHHELD,
    EvaluationChat,
    LlmAnswerer,
    UnavailableAnswerer,
)
from backend.stewardship.service import StewardshipService
from backend.stewardship.summary import ProviderError

from .test_app_flow import (  # noqa: F401 - fixtures
    CEFTRIAXONE,
    PATIENT,
    catalog,
    clock,
    pack,
    renal,
    store,
)


def model(*texts):
    """A fake provider that returns each text in turn and records every call."""
    calls = []

    def complete(system, user):
        calls.append((system, user))
        text = texts[min(len(calls), len(texts)) - 1]
        if isinstance(text, Exception):
            raise text
        return text

    complete.calls = calls
    return complete


@pytest.fixture
def make_client(catalog, pack, renal, store, clock, tmp_path):  # noqa: F811
    def make(answerer, max_questions=20):
        service = StewardshipService(
            catalog=catalog,
            rulepack=pack,
            renal=renal,
            audit=JsonlAuditLog(tmp_path / "audit.jsonl"),
            retriever=store,
            clock=clock["tick"],
        )
        chat = EvaluationChat(answerer, max_questions=max_questions)
        return TestClient(create_app(service, chat=chat))

    return make


def evaluate(client, **patient):
    body = {
        "patient": PATIENT | patient,
        "syndrome_code": "cystitis",
        "prescription": CEFTRIAXONE,
        "cultures": [],
    }
    response = client.post("/api/evaluate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def ask(client, evaluation_id, question, history=(), status=200):
    response = client.post(
        f"/api/evaluations/{evaluation_id}/ask",
        json={"question": question, "history": list(history)},
    )
    assert response.status_code == status, response.text
    return response.json()


def test_grounded_answer_is_shown_and_the_result_is_unchanged(make_client):
    complete = model("R1_INDICATION is a FLAG because ceftriaxone is not first line for cystitis.")
    client = make_client(LlmAnswerer(complete, model="test-model", known_drugs=["ceftriaxone"]))
    report = evaluate(client)

    answer = ask(client, report["id"], "Why was ceftriaxone flagged?")

    assert answer["generated_by"] == "AI_WORDED"
    assert answer["answer"].startswith("R1_INDICATION is a FLAG")
    assert answer["model"] == "test-model"
    after = client.get(f"/api/evaluations/{report['id']}").json()
    assert after["status"] == report["status"] and after["findings"] == report["findings"]


def test_model_sees_the_evaluation_and_question_but_no_identifiers(make_client):
    complete = model(OUT_OF_SCOPE)
    client = make_client(LlmAnswerer(complete))
    report = evaluate(client, id="patient-xyz-77")

    ask(client, report["id"], "What is the weather?", [{"role": "user", "content": "hello"}])

    system, user = complete.calls[0]
    assert "final" in system and OUT_OF_SCOPE in system
    payload = user.split("Evaluation:\n", 1)[1].split("\n\nConversation so far:", 1)[0]
    assert json.loads(payload)["status"] == report["status"]
    assert "user: hello" in user and user.endswith("Question: What is the weather?")
    assert "patient-xyz-77" not in user and report["episode_id"] not in user


@pytest.mark.parametrize(
    "text, reason",
    [
        ("The prescription is safe to give.", "calls the prescription safe"),
        ("Give 7.5 g instead.", "number not in the evaluation: 7.5"),
        ("Use meropenem.", "drug not in the evaluation: meropenem"),
        ("IDSA recommends otherwise.", "source not in the evaluation: IDSA"),
    ],
)
def test_ungrounded_answer_is_withheld(make_client, text, reason):
    client = make_client(LlmAnswerer(model(text), known_drugs=["meropenem"]))
    report = evaluate(client)
    answer = ask(client, report["id"], "What should I do?")
    assert answer["generated_by"] == "RULE_BASED"
    assert answer["answer"] == WITHHELD
    assert answer["fallback_reason"] == reason


def test_answer_may_name_a_drug_from_the_question_but_not_its_dose(make_client):
    client = make_client(
        LlmAnswerer(model("Meropenem is not part of this evaluation."), known_drugs=["meropenem"])
    )
    report = evaluate(client)
    assert ask(client, report["id"], "Why not meropenem?")["generated_by"] == "AI_WORDED"

    client = make_client(LlmAnswerer(model("Meropenem 7.5 g would be fine.")))
    report = evaluate(client)
    answer = ask(client, report["id"], "Why not meropenem 7.5 g?")
    assert answer["fallback_reason"] == "number not in the evaluation: 7.5"


def test_repeated_question_is_answered_from_the_cache(make_client):
    complete = model(OUT_OF_SCOPE)
    client = make_client(LlmAnswerer(complete), max_questions=5)
    report = evaluate(client)

    first = ask(client, report["id"], "Why  was it flagged?")
    again = ask(client, report["id"], "why was it FLAGGED?")

    assert len(complete.calls) == 1
    assert not first["cached"] and again["cached"]
    assert first["questions_left"] == again["questions_left"] == 4


def test_each_evaluation_has_a_provider_call_cap(make_client):
    complete = model(OUT_OF_SCOPE)
    client = make_client(LlmAnswerer(complete), max_questions=2)
    report = evaluate(client)

    ask(client, report["id"], "one")
    assert ask(client, report["id"], "two")["questions_left"] == 0
    limited = ask(client, report["id"], "three", status=429)
    assert "2 questions" in limited["detail"]
    assert ask(client, report["id"], "one")["cached"]  # a cached answer is still free
    assert len(complete.calls) == 2


def test_provider_failure_is_withheld_and_not_cached(make_client):
    complete = model(ProviderError("provider HTTP 429"), OUT_OF_SCOPE)
    client = make_client(LlmAnswerer(complete))
    report = evaluate(client)

    failed = ask(client, report["id"], "Why?")
    assert failed["answer"] == WITHHELD and failed["fallback_reason"] == "provider HTTP 429"
    retried = ask(client, report["id"], "Why?")
    assert retried["answer"] == OUT_OF_SCOPE and not retried["cached"]


def test_without_a_provider_no_call_is_made(make_client):
    client = make_client(UnavailableAnswerer())
    report = evaluate(client)
    answer = ask(client, report["id"], "Why?")
    assert answer["answer"] == UNAVAILABLE and answer["questions_left"] is None


def test_unknown_evaluation_and_oversized_question_are_rejected(make_client):
    client = make_client(UnavailableAnswerer())
    ask(client, "no-such-evaluation", "Why?", status=404)
    report = evaluate(client)
    ask(client, report["id"], "x" * 501, status=422)
