"""Typed Jev questions, complete response validation, and explicit selection policy.

The demo provider is deterministic plumbing, not a calibrated probability model.
It only recognizes catalog names/aliases and directly attached level labels.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .matching import validate_constraints
from .retrieval import evidence_for, mention_spans, retrieve

POLICY_VERSION = "selection-v1"


class ProviderError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def sanitize(value):
    """Recursively remove credential fields without discarding answer metadata."""
    if isinstance(value, dict):
        sanitized = {}
        private_fields = {"api_key", "authorization", "access_token", "secret", "password", "headers", "request_headers", "response_headers"}
        for key, item in value.items():
            normalized_key = str(key).casefold().replace("-", "_")
            if normalized_key in private_fields:
                continue
            # These are answer option IDs, not metadata field names. A legitimate
            # option named 'password' must retain its numeric probability.
            if key == "probabilities" and isinstance(item, dict) and all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in item.values()):
                sanitized[str(key)] = dict(item)
            else:
                sanitized[str(key)] = sanitize(item)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def _question(item: dict, kind: str) -> dict:
    category = item.get("category_label") or item["category_id"]
    definition = f"Filter: {item['label']}. Definition: {item.get('description', '')}. Category: {category}. Subcategory/context: {item.get('subcategory') or 'unspecified'}."
    if item.get("levels"):
        definition += " Allowed levels and operators: " + "; ".join(
            f"{level['label']} [id={level['id']}, dimension={level.get('dimension')}, exact={level.get('supports_exact', True)}, minimum={level.get('supports_minimum', True) and level.get('rank') is not None}]"
            for level in item["levels"]
        ) + "."
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


def _probability(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ProviderError("invalid_provider_response", f"Provider returned an invalid {label}.")
    return float(value)


def validate_response(response: dict, questions: dict) -> dict:
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
            _probability(answer.get("noul"), "Noul probability")
        else:
            probabilities = answer.get("probabilities")
            if not isinstance(probabilities, dict) or set(probabilities) != set(question["criteria"]):
                raise ProviderError("invalid_provider_response", "Provider omitted or invented a Choice option probability.")
            for value in probabilities.values():
                _probability(value, "option probability")
            if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=0.02):
                raise ProviderError("invalid_provider_response", "Provider option probabilities do not sum to one.")
            selected = answer.get("choice")
            if selected not in question["criteria"]:
                raise ProviderError("invalid_provider_response", "Provider selected an unsupported Choice option.")
            if probabilities[selected] + 1e-6 < max(probabilities.values()):
                raise ProviderError("invalid_provider_response", "Provider selected a Choice that does not have the highest probability.")
            _probability(answer.get("confidence"), "Choice confidence")
    return response


def _call_jev(state: dict, questions: dict, *, api_key, model, timeout_seconds, max_retries) -> dict:
    if not api_key or not str(api_key).strip():
        raise ProviderError("provider_not_configured", "Live Jev requires a backend TypeSafe API key.", 503)
    try:
        from typesafe_sdk import (
            Choice, Noul, RetryPolicy, TypeSafeAPIConnectionError, TypeSafeAPIError,
            TypeSafeAPIResponseValidationError, TypeSafeAPITimeoutError, TypeSafeClient, TypeSafeError,
        )
    except ImportError as exc:
        raise ProviderError("provider_not_installed", "Install backend dependencies with uv sync --project backend --locked from the repository root to use live Jev.", 503) from exc
    typed = {key: Noul(instructions=value["instructions"]) if value["type"] == "noul"
             else Choice(instructions=value["instructions"], criteria=value["criteria"])
             for key, value in questions.items()}
    try:
        retry = RetryPolicy(max_retries=max_retries, timeout=timeout_seconds,
                            http_statuses={429, 500, 502, 503, 504, 529}, backoff_max=5.0)
        with TypeSafeClient(api_key=api_key, model=model, timeout=timeout_seconds, retry=retry) as client:
            result = client.system_one(state=state, questions=typed)
        return sanitize(result.model_dump(mode="json"))
    except TypeSafeAPITimeoutError as exc:
        raise ProviderError("provider_timeout", "Jev timed out. Retry the analysis.", 504) from exc
    except TypeSafeAPIConnectionError as exc:
        raise ProviderError("provider_connection", "Could not reach Jev. Check connectivity and retry.", 503) from exc
    except TypeSafeAPIResponseValidationError as exc:
        raise ProviderError("invalid_provider_response", "Jev returned an invalid response. Retry the analysis.") from exc
    except TypeSafeAPIError as exc:
        status = exc.status
        if status in {401, 403}:
            raise ProviderError("provider_authentication", "Jev rejected the configured credentials. Check the backend API key.", 503) from exc
        if status == 429:
            raise ProviderError("provider_rate_limit", "Jev is rate limited. Wait briefly and retry.", 429) from exc
        if status in {529, 503}:
            raise ProviderError("provider_overloaded", "Jev is temporarily overloaded. Retry shortly.", 503) from exc
        raise ProviderError("provider_request_failed", "Jev could not complete this request. Check the model configuration and retry.") from exc
    except TypeSafeError as exc:
        # SDK exception strings may include the request body. Never expose them.
        raise ProviderError("provider_configuration", "Jev client configuration is invalid. Check the backend settings.", 503) from exc


def _status(probability: float, yes: float, no: float) -> str:
    return "selected" if probability >= yes else "rejected" if probability <= no else "uncertain"


def apply_policy(response: dict, questions: dict, mapping: dict, *, select_threshold=.7, reject_threshold=.3, max_filters_per_category=10) -> dict:
    validate_response(response, questions)
    decisions, grouped = [], {}
    for question_id, answer in response["answers"].items():
        meta = mapping[question_id]
        item, kind = meta["filter"], meta["kind"]
        noul = answer["type"] == "noul"
        probability = answer.get("noul") if noul else None
        confidence = None if noul else answer["confidence"]
        status = _status(probability if noul else confidence, select_threshold, reject_threshold)
        if not noul and answer["choice"] in {"unspecified", "unsupported"}:
            status = "unspecified" if answer["choice"] == "unspecified" else "unsupported"
        decision = {"question_id": question_id, "filter_id": item["id"], "filter_label": item["label"],
                    "question": questions[question_id]["instructions"], "primitive": answer["type"],
                    "kind": "level" if kind == "operator" else kind, "status": status,
                    "probability": probability, "confidence": confidence,
                    "probabilities": answer.get("probabilities"), "selected_value": str(answer["noul"]) if noul else answer["choice"],
                    "provenance": "jev", "threshold": reject_threshold if status == "rejected" else select_threshold}
        decisions.append(decision)
        grouped.setdefault(item["id"], {"item": item})[kind] = decision
    selected, category_counts = [], Counter()
    for filter_id, group in grouped.items():
        relevant, excluded, mandatory = (group[key] for key in ("relevance", "exclusion", "mandatory"))
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
                supported = (definition.get("rank") is not None and definition.get("supports_minimum", True)) if operator == "minimum" else definition.get("supports_exact", True)
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
        selected.append({"filter_id": filter_id, "mode": mode, "requirement": "mandatory" if mode == "exclude" or mandatory["status"] == "selected" else "preferred",
                         "level_id": level_id, "operator": operator, "source": "jev"})
    sanitized = sanitize(response)
    sanitized["selection_policy"] = {"select_threshold": select_threshold, "reject_threshold": reject_threshold,
                                     "uncertain_interval": [reject_threshold, select_threshold]}
    return {"filters": selected, "decisions": decisions, "provider_response": sanitized,
            "usage": response.get("usage") or {}, "model": response.get("model")}


_EXCLUSION = re.compile(r"\b(?:excluding|exclude|without|except|no|not|sans|sauf|exclure|excluant|sin|excepto|excluir)\b", re.I)
_PREFERRED = re.compile(r"\b(?:prefer(?:red|ably)?|optional|nice.to.have|souhait[ée]|id[ée]alement|preferible|opcional)\b", re.I)
_MINIMUM = re.compile(r"\b(?:at least|minimum|or higher|or above|au moins|ou plus|como m[ií]nimo|o superior)\b|>=", re.I)


def _demo_facts(state: str, item: dict) -> dict:
    evidence, origin, span = evidence_for(state, item)
    if not span:
        return {"relevance": False, "exclusion": False, "mandatory": False, "level": "unspecified", "operator": "unspecified", "evidence": None, "origin": "demo_logic"}
    start, end = span
    before = re.split(r"[,;.\n]|\b(?:and|but|et|mais|y|pero)\b", state[:start], flags=re.I)[-1][-70:]
    after = re.split(r"[,;.\n]|\b(?:and|but|et|mais|y|pero)\b", state[end:], flags=re.I)[0][:70]
    # Coordination stays within the scope of a negation: "without X and Y".
    # A positive introducer or contrast starts a new scope: "without X, with Y".
    exclusion_scope = re.split(r"[,;.\n]|\b(?:but|mais|pero|with|avec|con)\b", state[:start], flags=re.I)[-1]
    excluded = bool(_EXCLUSION.search(exclusion_scope))
    preferred = bool(_PREFERRED.search(before + " " + after))
    level_id = "unspecified"
    operator = "unspecified"
    for level in item.get("levels", []):
        level_spans = mention_spans(state, level["label"])
        for level_start, level_end in level_spans:
            between_after = state[end:level_start] if level_start >= end else None
            between_before = state[level_end:start] if level_end <= start else None
            adjacent_after = between_after is not None and re.fullmatch(r"\s*(?:(?:at|of|level|niveau|nivel)\s*)?[:=\-]?\s*", between_after, re.I)
            adjacent_before = between_before is not None and re.fullmatch(r"\s*(?:(?:in|en)\s*)?", between_before, re.I)
            if adjacent_after or adjacent_before:
                level_id = level["id"]
                operator = "minimum" if _MINIMUM.search(state[max(0, min(start, level_start)-25):max(end, level_end)+25]) else "exact"
                supported = (level.get("rank") is not None and level.get("supports_minimum", True)) if operator == "minimum" else level.get("supports_exact", True)
                if not supported:
                    level_id = "unsupported"
                break
        if level_id != "unspecified":
            break
    return {"relevance": not excluded, "exclusion": excluded, "mandatory": not preferred,
            "level": level_id, "operator": operator, "evidence": evidence, "origin": origin}


def _mock(state: str, candidates: list[dict], questions: dict, mapping: dict, max_filters_per_category: int) -> dict:
    answers, decisions, selected, category_counts = {}, [], [], Counter()
    facts = {item["id"]: _demo_facts(state, item) for item in candidates}
    for question_id, meta in mapping.items():
        item, kind = meta["filter"], meta["kind"]
        fact, primitive = facts[item["id"]], questions[question_id]["type"]
        value = fact[kind]
        status = ("selected" if value else "rejected") if isinstance(value, bool) else ("unspecified" if value == "unspecified" else "unsupported" if value == "unsupported" else "selected")
        answers[question_id] = {"type": primitive, "selected_value": value, "value_kind": "deterministic_rule"}
        if isinstance(value, bool):
            answers[question_id]["heuristic_value"] = int(value)
        decisions.append({"question_id": question_id, "filter_id": item["id"], "filter_label": item["label"],
                          "question": questions[question_id]["instructions"], "primitive": primitive,
                          "kind": "level" if kind == "operator" else kind, "status": status,
                          "probability": None, "confidence": None, "probabilities": None,
                          "selected_value": str(value).lower(), "provenance": "demo_logic",
                          "evidence": fact["evidence"], "threshold": None})
    for item in candidates:
        fact = facts[item["id"]]
        if not (fact["relevance"] or fact["exclusion"]) or fact["level"] == "unsupported":
            continue
        if not fact["exclusion"] and category_counts[item["category_id"]] >= max_filters_per_category:
            for decision in decisions:
                if decision["filter_id"] == item["id"] and decision["kind"] == "relevance":
                    decision["status"] = "limited"
            continue
        if not fact["exclusion"]:
            category_counts[item["category_id"]] += 1
        selected.append({"filter_id": item["id"], "mode": "exclude" if fact["exclusion"] else "include",
                         "requirement": "mandatory" if fact["mandatory"] or fact["exclusion"] else "preferred",
                         "level_id": None if fact["level"] == "unspecified" else fact["level"],
                         "operator": "exact" if fact["operator"] == "unspecified" else fact["operator"], "source": "demo_logic"})
    return {"filters": selected, "decisions": decisions,
            "provider_response": {"provider": "mock", "model": "deterministic-v1", "value_kind": "deterministic_rule",
                                  "notice": "Demo rule outputs are not Jev probabilities. Domain quality awaits user examples.", "answers": answers},
            "usage": {}, "model": "deterministic-v1"}


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
        return _mock(state_text, candidates, questions, mapping, max_filters_per_category)
    # Empty catalogs cannot produce typed questions; do not pretend a provider call ran.
    if not questions:
        raise ProviderError("no_candidate_filters", "No catalog filters match this state. Import a reviewed catalog or adjust the requirement.", 422)
    state = {"user_requirement": state_text, "current_filter_snapshot": current_filters,
             "snapshot_context": "Existing selections are UI context only, not evidence of the user's new requirement. Reevaluate them from user_requirement."}
    response = _call_jev(state, questions, api_key=api_key, model=model, timeout_seconds=timeout_seconds, max_retries=max_retries)
    return apply_policy(response, questions, mapping, select_threshold=select_threshold, reject_threshold=reject_threshold,
                        max_filters_per_category=max_filters_per_category)
