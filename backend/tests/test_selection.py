"""Small synthetic fixtures exercise rules; never imported as product data."""

import math

import pytest

from backend.app import selection
from backend.app.selection import ProviderError, analyze, apply_policy, build_questions, sanitize, validate_response
from backend.app.matching import search_profiles, validate_constraints
from backend.app.filter_search import normalize, retrieve


@pytest.fixture
def catalog():
    return [
        {"id": "cpp", "category_id": "tools", "label": "C++", "description": "A technical test fixture", "aliases": [], "levels": []},
        {"id": "c", "category_id": "tools", "label": "C", "description": "A different technical test fixture", "aliases": [], "levels": []},
        {"id": "req", "category_id": "tools", "label": "REQ-42", "description": "A requirements test tool", "aliases": ["outil exigences"], "levels": []},
        {"id": "lang", "category_id": "languages", "label": "Test Language", "description": "A synthetic language fixture", "aliases": [],
         "levels": [{"id": "b1", "label": "B1", "rank": 1, "dimension": "language"}, {"id": "b2", "label": "B2", "rank": 2, "dimension": "language"}, {"id": "c1", "label": "C1", "rank": 3, "dimension": "language"}]},
        {"id": "other", "category_id": "languages", "label": "Other Language", "description": "Another synthetic language", "aliases": [],
         "levels": [{"id": "other-b2", "label": "B2", "rank": 2, "dimension": "language"}]},
    ]


def constraint(filter_id, **kwargs):
    return {"filter_id": filter_id, "mode": "include", "requirement": "mandatory", "operator": "exact", "level_id": None, "source": "manual", **kwargs}


def profile(profile_id, facts):
    return {"id": profile_id, "display_name": profile_id, "title": "Test only", "summary": "Synthetic isolated fixture", "experience_years": 2, "competencies": facts, "languages": []}


def noul_response(questions, probability=.8):
    return {"model": "fixture", "answers": {question_id: {"type": "noul", "noul": probability} for question_id in questions}}


def test_normalization_preserves_identifiers():
    assert normalize("  C++ EN50128 B2 \n") == "c++ en50128 b2"


def test_exact_retrieval_never_confuses_c_with_cpp(catalog):
    assert [item["id"] for item in retrieve("Need C++", catalog, [])] == ["cpp"]


def test_multilingual_alias_preserves_original_evidence(catalog):
    result = analyze("Besoin de outil exigences", catalog, [])
    assert result["filters"][0]["filter_id"] == "req"
    assert result["decisions"][0]["evidence"] == "outil exigences"


def test_existing_filters_are_reevaluated_and_deselected(catalog):
    result = analyze("Need C++", catalog, [constraint("req")])
    assert [item["filter_id"] for item in result["filters"]] == ["cpp"]
    assert any(item["filter_id"] == "req" and item["status"] == "rejected" for item in result["decisions"])


def test_mock_does_not_fabricate_calibrated_probabilities(catalog):
    result = analyze("Need C++", catalog, [])
    assert all(item["probability"] is None and item["confidence"] is None for item in result["decisions"])
    assert result["provider_response"]["value_kind"] == "deterministic_rule"


@pytest.mark.parametrize("state", ["", "  ", "\n"])
def test_blank_state_never_calls_provider(state, monkeypatch):
    monkeypatch.setattr(selection, "call_jev", lambda *_args, **_kwargs: pytest.fail("provider called"))
    with pytest.raises(ValueError, match="blank"):
        analyze(state, [], [], provider="jev")


def test_no_taxonomy_or_description_implication(catalog):
    result = analyze("Need a requirements test tool", catalog, [])
    assert result["filters"] == []


def test_exclusion_is_separate_from_inclusion(catalog):
    result = analyze("Need C++, excluding REQ-42", catalog, [])
    assert {(item["filter_id"], item["mode"]) for item in result["filters"]} == {("cpp", "include"), ("req", "exclude")}


def test_levels_attach_to_specific_filter_and_minimum_is_explicit(catalog):
    result = analyze("Test Language B2 or higher, Other Language", catalog, [])
    constraints = {item["filter_id"]: item for item in result["filters"]}
    assert constraints["lang"]["level_id"] == "b2"
    assert constraints["lang"]["operator"] == "minimum"
    assert constraints["other"]["level_id"] is None
    exact = analyze("Test Language B2", catalog, [])["filters"][0]
    assert exact["operator"] == "exact"


def test_no_tool_level_inferred_from_experience(catalog):
    assert analyze("Experience with REQ-42", catalog, [])["filters"][0]["level_id"] is None


@pytest.mark.parametrize("value,expected", [(.7, "selected"), (.3, "rejected"), (.5, "uncertain")])
def test_threshold_boundaries(value, expected):
    assert selection._status(value, .7, .3) == expected


@pytest.mark.parametrize("value", [math.nan, math.inf, -.1, 1.1, True, "0.8", None])
def test_invalid_noul_values_rejected(value, catalog):
    questions, _ = build_questions(catalog[:1])
    with pytest.raises(ProviderError, match="invalid"):
        validate_response(noul_response(questions, value), questions)


def test_all_answer_ids_required(catalog):
    questions, _ = build_questions(catalog[:1])
    response = noul_response(questions)
    response["answers"].pop(next(iter(response["answers"])))
    with pytest.raises(ProviderError, match="IDs"):
        validate_response(response, questions)


def test_every_choice_probability_required(catalog):
    questions, _ = build_questions(catalog[3:4])
    response = noul_response(questions)
    for question_id, question in questions.items():
        if question["type"] == "choice":
            response["answers"][question_id] = {"type": "choice", "choice": "unspecified", "confidence": 1, "probabilities": {"unspecified": 1}}
    with pytest.raises(ProviderError, match="probability"):
        validate_response(response, questions)


def test_conflicting_inclusion_exclusion_retained_for_review(catalog):
    questions, mapping = build_questions(catalog[:1])
    result = apply_policy(noul_response(questions, .9), questions, mapping)
    assert result["filters"] == []
    assert len(result["decisions"]) == 3
    assert sum(item["status"] == "conflict" for item in result["decisions"]) == 2


def test_rejected_answers_survive_policy(catalog):
    questions, mapping = build_questions(catalog[:1])
    result = apply_policy(noul_response(questions, .1), questions, mapping)
    assert len(result["decisions"]) == len(questions)
    assert len(result["provider_response"]["answers"]) == len(questions)


def test_category_limits_preserve_dropped_decisions(catalog):
    result = analyze("C++ and REQ-42", catalog, [], max_filters_per_category=1)
    assert len(result["filters"]) == 1
    assert any(item["status"] == "limited" for item in result["decisions"])


def test_live_failure_does_not_fall_back(catalog, monkeypatch):
    def fail(*_args, **_kwargs):
        raise ProviderError("provider_timeout", "Test timeout", 504)
    monkeypatch.setattr(selection, "call_jev", fail)
    with pytest.raises(ProviderError) as error:
        analyze("C++", catalog, [], provider="jev", api_key="fixture")
    assert error.value.code == "provider_timeout"


def test_sanitization_keeps_values_and_removes_nested_credentials():
    assert sanitize({"answers": {"q": {"noul": .8}}, "authorization": "secret", "meta": {"api_key": "secret", "duration": 3}}) == {"answers": {"q": {"noul": .8}}, "meta": {"duration": 3}}


def test_invalid_level_attachment_rejected(catalog):
    with pytest.raises(ValueError, match="not allowed"):
        validate_constraints([constraint("req", level_id="b2")], catalog)


def test_conflicting_snapshot_rejected(catalog):
    with pytest.raises(ValueError, match="conflicting"):
        validate_constraints([constraint("cpp"), constraint("cpp", mode="exclude")], catalog)


def test_and_or_matching_and_unknown(catalog):
    profiles = [profile("one", [{"filter_id": "cpp"}]), profile("both", [{"filter_id": "cpp"}, {"filter_id": "req"}])]
    filters = [constraint("cpp"), constraint("req")]
    assert [row["profile"]["id"] for row in search_profiles(profiles, catalog, filters)] == ["both"]
    results = search_profiles(profiles, catalog, filters, grouping="or")
    assert len(results) == 2
    assert results[1]["unknown"] == ["REQ-42"]
    assert results[1]["unmet"] == []


def test_category_or_grouping_and_required_other_category(catalog):
    profiles = [profile("match", [{"filter_id": "cpp"}, {"filter_id": "lang"}]), profile("missing-domain", [{"filter_id": "cpp"}])]
    results = search_profiles(profiles, catalog, [constraint("cpp"), constraint("req"), constraint("lang")], category_grouping={"tools": "or"})
    assert [row["profile"]["id"] for row in results] == ["match"]


def test_minimum_level_compared_by_explicit_rank(catalog):
    profiles = [profile("higher", [{"filter_id": "lang", "level_id": "c1"}]), profile("exact", [{"filter_id": "lang", "level_id": "b2"}]), profile("unknown", [{"filter_id": "lang"}])]
    assert len(search_profiles(profiles, catalog, [constraint("lang", level_id="b2", operator="minimum")])) == 2
    assert [row["profile"]["id"] for row in search_profiles(profiles, catalog, [constraint("lang", level_id="b2")])] == ["exact"]


def test_unknown_exclusion_does_not_prove_absence(catalog):
    profiles = [profile("unknown", []), profile("known-absent", [{"filter_id": "req", "present": False}]), profile("present", [{"filter_id": "req"}])]
    result = search_profiles(profiles, catalog, [constraint("req", mode="exclude")])
    assert [row["profile"]["id"] for row in result] == ["known-absent"]


def test_preferred_unknown_remains_visible_without_disqualifying(catalog):
    result = search_profiles([profile("unknown", [])], catalog, [constraint("req", requirement="preferred")])
    assert result[0]["unknown"] == ["REQ-42"]
    assert result[0]["score"] == 0


def test_exact_mentions_cannot_be_silently_dropped_at_budget(catalog):
    with pytest.raises(ValueError, match="explicitly named"):
        retrieve("Need C++", catalog, [constraint("req")], budget=1)


def test_demo_category_cap_never_drops_exclusions(catalog):
    result = analyze("C++, excluding REQ-42", catalog, [], max_filters_per_category=1)
    assert {(item["filter_id"], item["mode"]) for item in result["filters"]} == {("cpp", "include"), ("req", "exclude")}


def test_live_category_cap_never_drops_exclusions(catalog):
    questions, mapping = build_questions([catalog[0], catalog[2]])
    response = noul_response(questions)
    for question_id, meta in mapping.items():
        excluded = meta["filter"]["id"] == "req"
        response["answers"][question_id]["noul"] = .9 if (meta["kind"] == "exclusion") == excluded or meta["kind"] == "mandatory" else .1
    result = apply_policy(response, questions, mapping, max_filters_per_category=1)
    assert {(item["filter_id"], item["mode"]) for item in result["filters"]} == {("cpp", "include"), ("req", "exclude")}


@pytest.mark.parametrize("operator,flag", [("exact", "supports_exact"), ("minimum", "supports_minimum")])
def test_link_operator_flags_enforced_in_matching_and_demo(catalog, operator, flag):
    catalog[3]["levels"][1][flag] = False
    with pytest.raises(ValueError, match="not supported"):
        validate_constraints([constraint("lang", level_id="b2", operator=operator)], catalog)
    state = "Test Language B2" + (" or higher" if operator == "minimum" else "")
    result = analyze(state, catalog, [])
    assert not result["filters"]
    assert any(item["status"] == "unsupported" for item in result["decisions"])


def test_minimum_cannot_compare_different_dimensions(catalog):
    catalog[3]["levels"][2]["dimension"] = "unrelated"
    result = search_profiles([profile("invalid", [{"filter_id": "lang", "level_id": "c1"}])], catalog,
                             [constraint("lang", level_id="b2", operator="minimum", requirement="preferred")])
    assert result[0]["unknown"] == ["Test Language (>= B2)"]


def test_unknown_recorded_level_is_unknown_for_exact(catalog):
    result = search_profiles([profile("invalid", [{"filter_id": "lang", "level_id": "foreign-level"}])], catalog,
                             [constraint("lang", level_id="b2", requirement="preferred")])
    assert result[0]["unknown"] == ["Test Language (B2)"]
    assert result[0]["unmet"] == []


def test_negation_scope_covers_and_list_and_resets_at_positive_clause(catalog):
    result = analyze("without C++ and REQ-42", catalog, [])
    assert all(item["mode"] == "exclude" for item in result["filters"])
    result = analyze("without C++ and with REQ-42", catalog, [])
    assert {item["filter_id"]: item["mode"] for item in result["filters"]} == {"cpp": "exclude", "req": "include"}


def test_sanitizer_preserves_legitimate_option_ids():
    probabilities = {"secret-level": .2, "password": .8}
    result = sanitize({"answers": {"q": {"probabilities": probabilities}}, "password": "credential"})
    assert result == {"answers": {"q": {"probabilities": probabilities}}}


def test_policy_rejected_threshold_is_recorded(catalog):
    questions, mapping = build_questions(catalog[:1])
    result = apply_policy(noul_response(questions, .1), questions, mapping)
    assert all(item["threshold"] == .3 for item in result["decisions"])
    assert result["provider_response"]["selection_policy"]["reject_threshold"] == .3


def test_question_includes_readable_subcategory(catalog):
    catalog[0]["subcategory"] = "Synthetic context"
    questions, _ = build_questions(catalog[:1])
    assert all("Synthetic context" in item["instructions"] for item in questions.values())
