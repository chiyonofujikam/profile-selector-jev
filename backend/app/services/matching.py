"""Transparent AND/OR matching with explicit unknown data and per-skill levels."""

from __future__ import annotations

from collections import defaultdict


def validate_constraints(filters: list[dict], catalog: list[dict]) -> None:
    by_id = {item["id"]: item for item in catalog}
    seen = set()
    for constraint in filters:
        filter_id = constraint["filter_id"]
        if filter_id not in by_id:
            raise ValueError(f"Unknown filter: {filter_id}")
        if filter_id in seen:
            raise ValueError(f"Duplicate or conflicting filter: {filter_id}")
        seen.add(filter_id)
        if constraint.get("mode", "include") not in {"include", "exclude"}:
            raise ValueError("Filter mode must be include or exclude.")
        if constraint.get("requirement", "mandatory") not in {"mandatory", "preferred"}:
            raise ValueError("Requirement must be mandatory or preferred.")
        if constraint.get("operator", "exact") not in {"exact", "minimum"}:
            raise ValueError("Level operator must be exact or minimum.")
        level_id = constraint.get("level_id")
        if level_id is None:
            if constraint.get("operator", "exact") == "minimum":
                raise ValueError("A minimum operator requires a level.")
            continue
        levels = {level["id"]: level for level in by_id[filter_id].get("levels", [])}
        if level_id not in levels:
            raise ValueError(f"Level {level_id} is not allowed for filter {filter_id}.")
        if constraint.get("operator", "exact") == "minimum":
            if levels[level_id].get("rank") is None or not levels[level_id].get("supports_minimum", True):
                raise ValueError("Minimum is not supported for this filter level.")
        elif not levels[level_id].get("supports_exact", True):
            raise ValueError("Exact matching is not supported for this filter level.")


def _evaluate(profile: dict, constraint: dict, item: dict) -> bool | None:
    facts = {fact["filter_id"]: fact for fact in [*profile.get("competencies", []), *profile.get("languages", [])]}
    fact = facts.get(constraint["filter_id"])
    if fact is None:
        return None  # absence of a competency record does not establish absence
    if fact.get("present") is False:
        return False
    wanted = constraint.get("level_id")
    if wanted is None:
        return True
    actual = fact.get("level_id")
    if actual is None:
        return None
    levels = {level["id"]: level for level in item.get("levels", [])}
    if actual not in levels or levels[actual].get("dimension") != levels[wanted].get("dimension"):
        return None
    if constraint.get("operator", "exact") == "exact":
        return actual == wanted
    if actual not in levels or levels[actual].get("rank") is None:
        return None
    return levels[actual]["rank"] >= levels[wanted]["rank"]


def search_profiles(
    profiles: list[dict], catalog: list[dict], filters: list[dict],
    grouping: str = "and", category_grouping: dict[str, str] | None = None,
) -> list[dict]:
    """Return eligible profiles; unknown hard constraints cannot establish eligibility.

    Exclusions are always ANDed. Required includes are grouped by category using
    category_grouping and combined using grouping. Preferred includes only rank.
    """
    if grouping not in {"and", "or"}:
        raise ValueError("Grouping must be and or or.")
    category_grouping = category_grouping or {}
    if any(value not in {"and", "or"} for value in category_grouping.values()):
        raise ValueError("Category grouping must be and or or.")
    validate_constraints(filters, catalog)
    by_id = {item["id"]: item for item in catalog}
    results = []
    for profile in profiles:
        matched, unmet, unknown = [], [], []
        required_groups: dict[str, list[bool]] = defaultdict(list)
        exclusions_pass = True
        matched_weight, total_weight = 0.0, 0.0
        for constraint in filters:
            item = by_id[constraint["filter_id"]]
            value = _evaluate(profile, constraint, item)
            excluded = constraint.get("mode", "include") == "exclude"
            satisfied = None if value is None else (not value if excluded else value)
            label = item["label"]
            if constraint.get("level_id"):
                level = next(level for level in item["levels"] if level["id"] == constraint["level_id"])
                label += f" ({'>= ' if constraint.get('operator') == 'minimum' else ''}{level['label']})"
            if excluded:
                label = "Exclude " + label
                exclusions_pass = exclusions_pass and satisfied is True
            elif constraint.get("requirement", "mandatory") == "mandatory":
                required_groups[item["category_id"]].append(satisfied is True)
            if satisfied is None:
                unknown.append(label)
            elif satisfied:
                matched.append(label)
            else:
                unmet.append(label)
            weight = 1.0 if constraint.get("requirement", "mandatory") == "mandatory" or excluded else 0.5
            total_weight += weight
            if satisfied is True:
                matched_weight += weight
        groups = [any(values) if category_grouping.get(category_id, grouping) == "or" else all(values)
                  for category_id, values in required_groups.items()]
        includes_pass = (any(groups) if grouping == "or" else all(groups)) if groups else True
        eligible = exclusions_pass and includes_pass
        if eligible:
            results.append({"profile": profile, "score": round(100 * matched_weight / total_weight, 1) if total_weight else 0.0,
                            "matched": matched, "unmet": unmet, "unknown": unknown, "eligible": True})
    return sorted(results, key=lambda row: (-row["score"], row["profile"]["display_name"].casefold(), row["profile"]["id"]))
