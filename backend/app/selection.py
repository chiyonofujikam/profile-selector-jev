"""Turn the user's text into selected filters: find, ask, then apply the answers."""

from __future__ import annotations

import math
from collections import Counter

from .matching import validate_constraints
from .filter_search import retrieve
from .jev import ProviderError, call_jev, sanitize
from .demo import analyze_demo

POLICY_VERSION = "selection-v1"


def _question(item: dict, kind: str) -> dict:
    definition = f"Filter: {item['label']}. Definition: {item.get('description', '')}. Category: {item['category_id']}. Subcategory/context: {item.get('subcategory') or 'unspecified'}."
    if item.get("levels"):
        descriptions = []
        for level in item["levels"]:
            exact = level.get("supports_exact", True)
            minimum = level.get("supports_minimum", True) and level.get("rank") is not None
            descriptions.append(
                f"{level['label']} [id={level['id']}, dimension={level.get('dimension')}, "
                f"exact={exact}, minimum={minimum}]"
            )
        definition += " Allowed levels and operators: " + "; ".join(descriptions) + "."
    instructions = {
        "relevance": "Does the user's requirement positively ask for this specific filter? Excluded filters are not positive requirements. Do not infer related specialties from taxonomy membership or infer relevance from the existing filter snapshot.",
        "exclusion": "Does the user's requirement explicitly exclude this specific filter? Lack of a mention is not an exclusion.",
        "mandatory": "Is this specific filter a mandatory requirement rather than a preference? Judge the user's text; existing filter settings are not evidence.",
        "level": "Which level is explicitly stated for this particular filter? Do not infer expertise from experience with a tool, levels on other skills, or years of experience. Use unspecified if none is stated, and unsupported if a stated level cannot map to the choices.",
        "operator": "For the explicitly stated level of this particular filter, does the user require that exact level or a minimum? A level label alone means exact. Choose unspecified if no level is stated, unsupported if the comparison cannot be represented.",
    }
    question = {"type": "noul" if kind in {"relevance", "exclusion", "mandatory"} else "choice",
                "instructions": instructions[kind] + " " + definition}
    if kind == "level":
        question["criteria"] = {level["id"]: level["label"] for level in item.get("levels", [])}
        question["criteria"].update({"unspecified": "No level explicitly attached to this filter", "unsupported": "A level was stated but none of the defined labels applies"})
    elif kind == "operator":
        question["criteria"] = {"exact": "Exactly the stated level; a bare level label means exact", "minimum": "An explicit minimum, at least, or higher", "unspecified": "No level stated", "unsupported": "Unsupported comparison, such as maximum"}
    return question


def build_questions(candidates: list[dict]) -> tuple[dict, dict]:
    questions, mapping = {}, {}
    for index, item in enumerate(candidates):
        kinds = ["relevance", "exclusion", "mandatory"]
        if item.get("levels"):
            kinds.extend(["level", "operator"])
        for kind in kinds:
            question_id = f"q{index}_{kind}"
            questions[question_id] = _question(item, kind)
            mapping[question_id] = {"filter": item, "kind": kind}
    return questions, mapping


def _validate_probability(value, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ProviderError("invalid_provider_response", f"Provider returned an invalid {label}.")


def validate_response(response: dict, questions: dict) -> None:
    """Reject missing/unexpected IDs, invalid numeric ranges, and partial distributions."""
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise ProviderError("invalid_provider_response", "Provider response has no answer mapping.")
    answers = response["answers"]
    if set(answers) != set(questions):
        raise ProviderError("invalid_provider_response", "Provider answer IDs do not match the submitted questions.")
    for question_id, question in questions.items():
        answer = answers[question_id]
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ProviderError("invalid_provider_response", "Provider answer primitive does not match its question.")
        if question["type"] == "noul":
            _validate_probability(answer.get("noul"), "Noul probability")
        else:
            probabilities = answer.get("probabilities")
            if not isinstance(probabilities, dict) or set(probabilities) != set(question["criteria"]):
                raise ProviderError("invalid_provider_response", "Provider omitted or invented a Choice option probability.")
            for value in probabilities.values():
                _validate_probability(value, "option probability")
            if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.02):
                raise ProviderError("invalid_provider_response", "Provider option probabilities do not sum to one.")
            selected = answer.get("choice")
            if selected not in question["criteria"]:
                raise ProviderError("invalid_provider_response", "Provider selected an unsupported Choice option.")
            if probabilities[selected] + 1e-6 < max(probabilities.values()):
                raise ProviderError("invalid_provider_response", "Provider selected a Choice that does not have the highest probability.")
            _validate_probability(answer.get("confidence"), "Choice confidence")


def _status(probability: float, yes: float, no: float) -> str:
    if probability >= yes:
        return "selected"
    if probability <= no:
        return "rejected"
    return "uncertain"


def make_decision(question_id, question, answer, item, kind, select_threshold, reject_threshold):
    """Prepare one answer for the response panel."""
    probability = None
    confidence = None
    if answer["type"] == "noul":
        probability = answer["noul"]
        selected_value = str(probability)
        status = _status(probability, select_threshold, reject_threshold)
    else:
        confidence = answer["confidence"]
        selected_value = answer["choice"]
        status = _status(confidence, select_threshold, reject_threshold)
        if selected_value in {"unspecified", "unsupported"}:
            status = selected_value

    if kind == "operator":
        kind = "level"
    threshold = select_threshold
    if status == "rejected":
        threshold = reject_threshold

    return {
        "question_id": question_id,
        "filter_id": item["id"],
        "filter_label": item["label"],
        "question": question["instructions"],
        "primitive": answer["type"],
        "kind": kind,
        "status": status,
        "probability": probability,
        "confidence": confidence,
        "probabilities": answer.get("probabilities"),
        "selected_value": selected_value,
        "provenance": "jev",
        "threshold": threshold,
    }


def apply_policy(response: dict, questions: dict, mapping: dict, *, select_threshold=.7, reject_threshold=.3, max_filters_per_category=10) -> dict:
    validate_response(response, questions)
    decisions = []
    grouped = {}
    for question_id, answer in response["answers"].items():
        meta = mapping[question_id]
        item = meta["filter"]
        kind = meta["kind"]
        decision = make_decision(
            question_id, questions[question_id], answer, item, kind,
            select_threshold, reject_threshold,
        )
        decisions.append(decision)
        grouped.setdefault(item["id"], {"item": item})[kind] = decision
    selected, category_counts = [], Counter()
    for filter_id, group in grouped.items():
        relevant = group["relevance"]
        excluded = group["exclusion"]
        mandatory = group["mandatory"]
        if relevant["status"] == "selected" and excluded["status"] == "selected":
            relevant["status"] = excluded["status"] = "conflict"
            continue
        if excluded["status"] == "selected":
            mode = "exclude"
        elif relevant["status"] == "selected" and excluded["status"] == "rejected":
            mode = "include"
        else:
            continue
        if mode == "include" and mandatory["status"] == "uncertain":
            relevant["status"] = "uncertain"
            continue
        level_id, operator = None, "exact"
        if "level" in group:
            level, comparison = group["level"], group["operator"]
            if level["status"] in {"uncertain", "unsupported", "rejected"}:
                relevant["status"] = "uncertain"
                continue
            if level["status"] == "selected":
                if comparison["status"] != "selected":
                    relevant["status"] = "uncertain"
                    continue
                level_id, operator = level["selected_value"], comparison["selected_value"]
                definition = next(level for level in group["item"]["levels"] if level["id"] == level_id)
                if operator == "minimum":
                    supported = definition.get("rank") is not None and definition.get("supports_minimum", True)
                else:
                    supported = definition.get("supports_exact", True)
                if not supported:
                    level["status"] = "unsupported"
                    relevant["status"] = "uncertain"
                    continue
        category_id = group["item"]["category_id"]
        if mode == "include" and category_counts[category_id] >= max_filters_per_category:
            relevant["status"] = "limited"
            continue
        if mode == "include":
            category_counts[category_id] += 1
        requirement = "preferred"
        if mode == "exclude" or mandatory["status"] == "selected":
            requirement = "mandatory"
        selected.append({
            "filter_id": filter_id,
            "mode": mode,
            "requirement": requirement,
            "level_id": level_id,
            "operator": operator,
            "source": "jev",
        })
    sanitized = sanitize(response)
    sanitized["selection_policy"] = {"select_threshold": select_threshold, "reject_threshold": reject_threshold,
                                     "uncertain_interval": [reject_threshold, select_threshold]}
    return {"filters": selected, "decisions": decisions, "provider_response": sanitized,
            "usage": response.get("usage") or {}, "model": response.get("model")}


def analyze(
    state_text: str, catalog: list[dict], current_filters: list[dict], *, provider="mock", model="jev-latest", api_key=None,
    timeout_seconds=30, max_retries=2, candidate_budget=30, select_threshold=.7, reject_threshold=.3, max_filters_per_category=10,
) -> dict:
    if not state_text or not state_text.strip():
        raise ValueError("State for Jev must not be blank.")
    if len(state_text) > 12000:
        raise ValueError("State for Jev must be at most 12000 characters.")
    if not 0 <= reject_threshold < select_threshold <= 1:
        raise ValueError("Decision thresholds must satisfy 0 <= reject < select <= 1.")
    if provider not in {"mock", "jev"}:
        raise ValueError("Unknown decision provider.")
    if not 1 <= candidate_budget <= 100 or not 1 <= max_filters_per_category <= 100:
        raise ValueError("Filter budgets must be between 1 and 100.")
    validate_constraints(current_filters, catalog)
    candidates = retrieve(state_text, catalog, current_filters, candidate_budget)
    questions, mapping = build_questions(candidates)
    if provider == "mock":
        return analyze_demo(state_text, candidates, questions, mapping, max_filters_per_category)
    # Empty catalogs cannot produce typed questions; do not pretend a provider call ran.
    if not questions:
        raise ProviderError("no_candidate_filters", "No catalog filters match this state. Import a reviewed catalog or adjust the requirement.", 422)
    state = {"user_requirement": state_text, "current_filter_snapshot": current_filters,
             "snapshot_context": "Existing selections are UI context only, not evidence of the user's new requirement. Reevaluate them from user_requirement."}
    response = call_jev(state, questions, api_key=api_key, model=model, timeout_seconds=timeout_seconds, max_retries=max_retries)
    return apply_policy(response, questions, mapping, select_threshold=select_threshold, reject_threshold=reject_threshold,
                        max_filters_per_category=max_filters_per_category)
