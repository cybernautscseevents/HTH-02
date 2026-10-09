"""The evaluation summary explains the deterministic result and can never change it.

A model's text is checked before it is shown; anything it cannot be trusted with (an unstated
CANNOT_ASSESS, an invented number or drug, a failed call) falls back to the deterministic summary.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.stewardship import config, summary
from backend.stewardship.api import create_app
from backend.stewardship.audit import JsonlAuditLog
from backend.stewardship.schemas import Evaluation
from backend.stewardship.service import StewardshipService
from backend.stewardship.summary import (
    LlmSummarizer,
    OpenAICompatibleProvider,
    ProviderError,
    TemplateSummarizer,
    antibiotic_names,
    evidence_for,
    grounding_problem,
    summarizer_from_env,
)

from .test_app_flow import (  # noqa: F401 - fixtures
    CEFTRIAXONE,
    NITRO,
    PATIENT,
    catalog,
    clock,
    pack,
    renal,
    store,
)

NO_FREQUENCY = "Tab Nitrofurantoin 100 mg x 5 days"
# inputs_hash is left out: it covers the episode id, which is new for every request.
RESULT_FIELDS = ("status", "findings", "ruleset_version", "culture", "warnings")


@pytest.fixture
def make_client(catalog, pack, renal, store, clock, tmp_path):  # noqa: F811
    def make(summarizer=None):
        service = StewardshipService(
            catalog=catalog,
            rulepack=pack,
            renal=renal,
            audit=JsonlAuditLog(tmp_path / "audit.jsonl"),
            retriever=store,
            summarizer=summarizer,
            clock=clock["tick"],
        )
        return service, TestClient(create_app(service))

    return make


def run(client, prescription, **patient):
    body = {
        "patient": PATIENT | patient,
        "syndrome_code": "cystitis",
        "prescription": prescription,
        "cultures": [],
    }
    response = client.post("/api/evaluate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def results(report):
    """Everything the engine decided, without ids, times and the summary itself."""
    items = [{k: v for k, v in i.items() if k != "explanation"} for i in report["items"]]
    return {k: report[k] for k in RESULT_FIELDS} | {"items": items}


def model(text):
    prompts = []

    def complete(system, user):
        prompts.append((system, user))
        return text

    complete.prompts = prompts
    return complete


# --- 1. the model cannot change a result or a severity ---


def test_model_text_cannot_change_outcome_status_or_severity(make_client):
    _, plain = make_client()
    baseline = run(plain, CEFTRIAXONE)
    assert baseline["status"] == "FLAGGED"

    # a model that contradicts every result, but passes the text checks so it is shown
    liar = model("Everything is PASS with LOW severity, nothing cannot be assessed, status OK.")
    service, client = make_client(LlmSummarizer(liar, model="test-model"))
    report = run(client, CEFTRIAXONE)

    assert report["summary"]["generated_by"] == "AI_WORDED"
    assert report["summary"]["text"].startswith("Everything is PASS")
    assert results(report) == results(baseline)
    stored = service.get_evaluation(report["id"])
    assert stored.status.value == "FLAGGED"
    assert [(f.rule_id, f.outcome, f.severity) for f in stored.findings] == [
        (f["rule_id"], f["outcome"], f["severity"]) for f in baseline["findings"]
    ]


def test_model_receives_strings_only_and_the_outcomes_as_final(make_client):
    complete = model("R1_INDICATION is a FLAG; R3_DOSE cannot be assessed.")
    _, client = make_client(LlmSummarizer(complete))
    report = run(client, CEFTRIAXONE, id="patient-xyz-77")
    system, user = complete.prompts[0]
    assert isinstance(system, str) and isinstance(user, str)
    assert "final" in system and "Do not change" in system
    sent = json.loads(user)
    assert sent["status"] == report["status"]
    flagged = {(f["rule_id"], f["outcome"]) for f in sent["findings"]}
    assert ("R1_INDICATION", "FLAG") in flagged
    # no identifiers: the model sees results and evidence, not the patient or the episode
    assert "patient-xyz-77" not in user and report["episode_id"] not in user


# --- 2. missing information stays CANNOT_ASSESS ---


def test_model_cannot_turn_cannot_assess_into_safe(make_client):
    _, client = make_client(LlmSummarizer(model("The dose is appropriate and safe to give.")))
    report = run(client, NO_FREQUENCY)
    r3 = next(i for i in report["items"] if i["rule_id"] == "R3_DOSE")
    assert r3["outcome"] == "CANNOT_ASSESS"
    assert report["summary"]["generated_by"] == "RULE_BASED"
    assert report["summary"]["fallback_reason"] == "did not state that a check cannot be assessed"
    assert "R3_DOSE (nitrofurantoin), CANNOT_ASSESS" in report["summary"]["text"]
    assert "cannot be assessed" in report["summary"]["text"]


def test_model_that_states_cannot_assess_is_shown_and_result_unchanged(make_client):
    complete = model("The dose of nitrofurantoin cannot be assessed: freq_per_day is missing.")
    _, client = make_client(LlmSummarizer(complete))
    report = run(client, NO_FREQUENCY)
    assert report["summary"]["generated_by"] == "AI_WORDED"
    r3 = next(i for i in report["items"] if i["rule_id"] == "R3_DOSE")
    assert r3["outcome"] == "CANNOT_ASSESS"
    sent = next(
        f for f in json.loads(complete.prompts[0][1])["findings"] if f["rule_id"] == "R3_DOSE"
    )
    assert sent["outcome"] == "CANNOT_ASSESS" and sent["missing_inputs"] == ["freq_per_day"]


def test_deterministic_summary_names_every_cannot_assess(make_client):
    _, client = make_client()
    report = run(client, NO_FREQUENCY)
    unassessed = [i for i in report["items"] if i["outcome"] == "CANNOT_ASSESS"]
    assert unassessed
    for item in unassessed:
        assert f"{item['rule_id']} ({item['drug']}), CANNOT_ASSESS" in report["summary"]["text"]


# --- 3. the output is explanation only ---


@pytest.mark.parametrize(
    "text, reason",
    [
        ("Nitrofurantoin 400 mg would be preferred.", "number not in the evaluation: 400"),
        ("The course runs 14 days.", "number not in the evaluation: 14"),
        (
            "The course runs two weeks.",
            "dose, duration or frequency not in the evaluation: 'two weeks'",
        ),
        (
            "Nitrofurantoin is taken twice daily.",
            "dose, duration or frequency not in the evaluation: 'twice'",
        ),
        ("Colistin would also cover this.", "drug not in the evaluation: colistin"),
        ("A carbapenem would also cover this.", "drug not in the evaluation: carbapenem"),
        ("Augmentin would also cover this.", "drug not in the evaluation: augmentin"),
    ],
)
def test_invented_dose_duration_or_drug_is_not_shown(make_client, text, reason):
    complete = model(text)
    _, client = make_client(LlmSummarizer(complete, known_drugs=antibiotic_names()))
    report = run(client, NITRO)
    sent = complete.prompts[0][1].lower()
    assert all(w not in sent for w in ("colistin", "carbapenem", "augmentin", "twice"))
    assert report["summary"]["generated_by"] == "RULE_BASED"
    assert report["summary"]["fallback_reason"] == reason
    assert text not in report["summary"]["text"]


def test_summary_is_outside_the_engine_result_and_labelled(make_client):
    assert "summary" not in Evaluation.model_fields  # the engine's result has no summary
    _, client = make_client(
        LlmSummarizer(model("R1_INDICATION is a FLAG; R3_DOSE cannot be assessed."), model="m")
    )
    report = run(client, CEFTRIAXONE)
    s = report["summary"]
    assert (s["generated_by"], s["model"]) == ("AI_WORDED", "m")
    assert "does not determine the clinical result" in s["notice"]
    # the per-finding explanations and actions are still the deterministic ones
    _, plain = make_client()
    assert [i["explanation"] for i in report["items"]] == [
        i["explanation"] for i in run(plain, CEFTRIAXONE)["items"]
    ]


def test_sources_come_from_the_evidence_given(make_client):
    service, client = make_client()
    report = run(client, CEFTRIAXONE)
    stored = service.get_evaluation(report["id"])
    citations = {p.citation for p in evidence_for(stored)}
    assert citations and citations <= set(report["summary"]["sources"])


# --- 4. provider failure falls back to the deterministic explanation ---


def _raise(exc):
    def complete(system, user):
        raise exc

    return complete


@pytest.mark.parametrize(
    "complete, reason",
    [
        (_raise(RuntimeError("down")), "provider error (RuntimeError)"),
        (_raise(httpx.ConnectTimeout("timed out")), "provider timeout"),
        (model(""), "empty response"),
        (model("   "), "empty response"),
        (model("x" * 2001), "response too long"),
    ],
)
def test_provider_failure_falls_back_to_deterministic_summary(make_client, complete, reason):
    service, client = make_client(LlmSummarizer(complete, model="m"))
    report = run(client, CEFTRIAXONE)
    _, plain = make_client()
    baseline = run(plain, CEFTRIAXONE)
    assert results(report) == results(baseline)
    s = report["summary"]
    assert (s["generated_by"], s["fallback_reason"]) == ("RULE_BASED", reason)
    assert s["text"] == baseline["summary"]["text"]
    stored = service.get_evaluation(report["id"])
    expected = TemplateSummarizer().explain(stored, evidence_for(stored))
    assert s["text"] == expected.text


def test_openai_compatible_provider_request_and_http_failure(make_client):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "R2 is a FLAG; R3 cannot be assessed."}}]
                },
            )
        return httpx.Response(503)

    provider = OpenAICompatibleProvider(
        "http://llm.test/v1",
        "m",
        api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    _, client = make_client(LlmSummarizer(provider, model="m"))

    first = run(client, CEFTRIAXONE)
    assert first["summary"]["generated_by"] == "AI_WORDED"
    assert first["summary"]["text"] == "R2 is a FLAG; R3 cannot be assessed."
    assert sent[0]["model"] == "m" and sent[0]["temperature"] == 0 and sent[0]["max_tokens"]
    assert [m["role"] for m in sent[0]["messages"]] == ["system", "user"]

    second = run(client, CEFTRIAXONE)  # HTTP 503
    assert second["summary"]["generated_by"] == "RULE_BASED"
    assert second["summary"]["fallback_reason"] == "provider HTTP 503"
    assert results(second) == results(first)


def test_provider_is_configured_by_environment(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(config, "LLM_API_KEYS", ())
    assert isinstance(summarizer_from_env(), TemplateSummarizer)
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(config, "LLM_MODEL", "qwen2.5:7b")
    configured = summarizer_from_env()
    assert isinstance(configured, summary.LlmSummarizer)
    assert configured._model == "qwen2.5:7b"


# --- 5. off unless configured: no provider, model or key means no API call ---


@pytest.mark.parametrize(
    "env",
    [
        {},  # nothing configured
        {"LLM_PROVIDER": "groq"},  # hosted provider without a key
        {"LLM_PROVIDER": "gemini", "LLM_MODEL": "gemini-3.5-flash"},
        {"LLM_PROVIDER": "no-such-provider", "LLM_API_KEY": "k"},
        {"LLM_MODEL": "m"},  # no endpoint
    ],
)
def test_llm_disabled_gives_rule_based_summary_without_a_call(make_client, monkeypatch, env):
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.setattr(config, name, env.get(name))
    monkeypatch.setattr(
        config, "LLM_API_KEYS", (env["LLM_API_KEY"],) if env.get("LLM_API_KEY") else ()
    )
    monkeypatch.setattr(
        summary.OpenAICompatibleProvider,
        "__init__",
        lambda *a, **k: pytest.fail("no provider may be built, so no API call can be made"),
    )
    summarizer = summarizer_from_env()
    assert isinstance(summarizer, TemplateSummarizer)
    _, client = make_client(summarizer)
    report = run(client, CEFTRIAXONE)
    s = report["summary"]
    assert (s["generated_by"], s["model"], s["fallback_reason"]) == ("RULE_BASED", None, None)


def test_hosted_provider_preset(monkeypatch):
    for name in ("LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(config, "LLM_PROVIDER", "Groq")
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(config, "LLM_API_KEYS", ("k",))
    configured = summarizer_from_env()
    assert isinstance(configured, LlmSummarizer)
    assert configured._model == summary.PROVIDERS["groq"][1]
    assert configured._complete._url == "https://api.groq.com/openai/v1/chat/completions"


# --- 6. the model may only restate; new advice, sources or reassurance are rejected ---


@pytest.mark.parametrize(
    "prescription, text, reason",
    [
        (NITRO, "Stop nitrofurantoin now.", "recommendation not in the evaluation: 'stop'"),
        (NITRO, "Add a second antibiotic.", "recommendation not in the evaluation: 'add'"),
        (NITRO, "Switch the antibiotic.", "recommendation not in the evaluation: 'switch'"),
        (NITRO, "Increase the dose.", "recommendation not in the evaluation: 'increase'"),
        (NITRO, "Nitrofurantoin is safe here.", "calls the prescription safe"),
        (NITRO, "This follows IDSA guidance.", "source not in the evaluation: IDSA"),
        (NITRO, "Per the Sanford Guide this is fine.", "source not in the evaluation: sanford"),
        (
            NO_FREQUENCY,
            "The dose cannot be assessed, but there are no issues.",
            "contradicts a flagged or unassessed check: 'no issues'",
        ),
    ],
)
def test_new_advice_source_or_reassurance_is_not_shown(make_client, prescription, text, reason):
    _, client = make_client(LlmSummarizer(model(text), known_drugs=antibiotic_names()))
    report = run(client, prescription)
    assert report["summary"]["generated_by"] == "RULE_BASED"
    assert report["summary"]["fallback_reason"] == reason


def test_an_effect_worded_with_a_dose_verb_is_not_advice():
    # An interaction described as "may increase the risk" is not a recommendation to increase.
    data = {"findings": [{"outcome": "FLAG", "suggested_action": None}]}
    text = "Paracetamol may increase the risk of methemoglobinemia with nitrofurantoin."
    assert grounding_problem(text, "nitrofurantoin paracetamol", data, ()) is None
    assert "increase" in grounding_problem("Increase the dose.", "", data, ())


def test_restating_the_rules_own_action_is_shown(make_client):
    # ceftriaxone for cystitis: the rules suggest a switch and a culture, so saying so is allowed
    text = (
        "Ceftriaxone is flagged: it is not listed for uncomplicated cystitis and is a Watch "
        "antibiotic; the rules suggest a switch to nitrofurantoin and to send a culture. "
        "R3_DOSE cannot be assessed (NCDC)."
    )
    _, client = make_client(LlmSummarizer(model(text), known_drugs=antibiotic_names()))
    report = run(client, CEFTRIAXONE)
    assert report["summary"]["generated_by"] == "AI_WORDED", report["summary"]["fallback_reason"]


# --- 7. provider transport: timeout, HTTP error, unreadable body, and the key stays secret ---

SECRET = "sk-test-SECRET-0123456789"


def _provider(handler, **kw):
    return OpenAICompatibleProvider(
        "http://llm.test/v1",
        "m",
        api_key=SECRET,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kw,
    )


def _timeout(request):
    raise httpx.ReadTimeout("read timed out", request=request)


def _refused(request):
    raise httpx.ConnectError(f"refused, key {SECRET}", request=request)


@pytest.mark.parametrize(
    "handler, reason",
    [
        (_timeout, "provider timeout"),
        (_refused, "provider unreachable (ConnectError)"),
        (lambda r: httpx.Response(401, json={"error": f"bad key {SECRET}"}), "provider HTTP 401"),
        (lambda r: httpx.Response(429, text="rate limited"), "provider HTTP 429"),
        (lambda r: httpx.Response(200, text="not json"), "provider response not readable"),
        (lambda r: httpx.Response(200, json={"choices": []}), "provider response not readable"),
    ],
)
def test_provider_failure_is_reported_without_the_key(make_client, caplog, handler, reason):
    caplog.set_level("DEBUG")
    provider = _provider(handler)
    _, client = make_client(LlmSummarizer(provider, model="m"))
    report = run(client, CEFTRIAXONE)
    assert report["summary"]["generated_by"] == "RULE_BASED"
    assert report["summary"]["fallback_reason"] == reason
    assert SECRET not in json.dumps(report)
    assert SECRET not in caplog.text
    assert SECRET not in repr(provider)
    assert "Traceback" not in caplog.text


def test_provider_rotates_to_the_next_key_after_rate_limit():
    authorizations = []

    def handler(request):
        authorizations.append(request.headers.get("authorization"))
        if authorizations[-1] == "Bearer first-key":
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json={"choices": [{"message": {"content": "summary"}}]})

    provider = OpenAICompatibleProvider(
        "http://llm.test/v1",
        "m",
        api_keys=("first-key", "second-key"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert provider("system", "user") == "summary"
    assert authorizations == ["Bearer first-key", "Bearer second-key"]
    assert "first-key" not in repr(provider) and "second-key" not in repr(provider)


def keyed_provider(keys, limited, now):
    """A provider over `keys` where every key in `limited` answers 429; records each key used."""
    used = []

    def handler(request):
        key = request.headers["authorization"].removeprefix("Bearer ")
        used.append(key)
        if key in limited:
            return httpx.Response(429, headers={"retry-after": "30"}, text="rate limited")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        "http://llm.test/v1",
        "m",
        api_keys=keys,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: now[0],
    )
    return provider, used


def test_provider_takes_keys_in_turn():
    provider, used = keyed_provider(("a", "b", "c"), limited=set(), now=[0.0])
    for _ in range(4):
        provider("system", "user")
    assert used == ["a", "b", "c", "a"]


def test_rate_limited_key_rests_for_retry_after():
    now = [0.0]
    limited = {"a"}
    provider, used = keyed_provider(("a", "b"), limited, now)

    provider("system", "user")
    provider("system", "user")
    assert used == ["a", "b", "b"]  # "a" answered 429 and is skipped while it rests

    limited.clear()
    now[0] = 31.0  # past the provider's Retry-After
    provider("system", "user")
    assert used[-1] == "a"


def test_no_call_is_made_while_every_key_rests():
    now = [0.0]
    provider, used = keyed_provider(("a", "b"), {"a", "b"}, now)
    with pytest.raises(ProviderError, match="provider HTTP 429"):
        provider("system", "user")
    assert used == ["a", "b"]
    with pytest.raises(ProviderError, match="every key resting"):
        provider("system", "user")
    assert used == ["a", "b"]


def test_summary_and_chat_share_one_provider(monkeypatch):
    from backend.stewardship.chat import answerer_from_env

    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.setattr(config, name, None)
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "LLM_API_KEYS", ("k1", "k2"))
    assert summarizer_from_env()._complete is answerer_from_env()._complete


def test_provider_request_holds_only_results_and_evidence(make_client):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "R3_DOSE cannot be assessed."}}]}
        )

    _, client = make_client(LlmSummarizer(_provider(handler), model="m"))
    report = run(client, NO_FREQUENCY, id="patient-xyz-77", age_years=63, weight_kg=71.5)
    (request,) = requests
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    body = request.content.decode()
    assert SECRET not in body  # the key travels in the header only
    user = json.loads(json.loads(body)["messages"][1]["content"])
    assert set(user) == {
        "status",
        "syndrome",
        "culture",
        "warnings",
        "findings",
        "passed_checks",
        "guideline_evidence",
    }
    for finding in user["findings"]:
        assert set(finding) == {
            "rule_id",
            "check",
            "outcome",
            "severity",
            "drug",
            "message",
            "recommended_action",
            "suggested_action",
            "missing_inputs",
            "sources",
        }
    for private in (
        "patient-xyz-77",
        report["episode_id"],
        report["id"],
        report["inputs_hash"],
        report["ruleset_version"],
        "71.5",
        '"age_years"',
        '"sex"',
    ):
        assert private not in body


def test_deterministic_summary_names_a_drug_interaction_explicitly():
    from types import SimpleNamespace

    from backend.stewardship.schemas import Outcome
    from backend.stewardship.summary import TemplateSummarizer

    item = SimpleNamespace(
        rule_id="DDI_INTERACTION:amoxicillin+paracetamol",
        drug="amoxicillin + paracetamol",
        outcome=Outcome.FLAG,
        severity="MODERATE",
        explanation="DrugBank reports an interaction between amoxicillin and paracetamol.",
        action="Review the reported interaction with the pharmacist.",
        evidence=(),
    )
    evaluation = SimpleNamespace(
        status=SimpleNamespace(value="FLAGGED"),
        items=[item],
        culture=SimpleNamespace(state="OK", action=None, message=""),
    )
    text = TemplateSummarizer().explain(evaluation, []).text
    assert "Drug–drug interaction (amoxicillin + paracetamol), FLAG MODERATE" in text
    assert "DDI_INTERACTION" not in text
