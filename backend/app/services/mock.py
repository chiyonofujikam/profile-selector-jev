"""Local demo rules; outputs are not model probabilities."""

import re
from collections import Counter

from .retrieval import evidence_for, mention_spans

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

