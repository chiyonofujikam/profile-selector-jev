"""Compare each profile with the filters selected on the page."""


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


def matches_filter(facts: dict, constraint: dict, item: dict) -> bool | None:
    """True means a match, False means no match, None means missing information."""
    fact = facts.get(constraint["filter_id"])
    if fact is None:
        return None
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
    if levels[actual].get("rank") is None:
        return None
    return levels[actual]["rank"] >= levels[wanted]["rank"]


def matches_group(results: list[bool], grouping: str) -> bool:
    if not results:
        return True
    if grouping == "or":
        return any(results)
    return all(results)


def filter_label(constraint: dict, item: dict) -> str:
    label = item["label"]
    if constraint.get("level_id"):
        for level in item["levels"]:
            if level["id"] == constraint["level_id"]:
                comparison = ""
                if constraint.get("operator") == "minimum":
                    comparison = ">= "
                label += f" ({comparison}{level['label']})"
                break
    if constraint.get("mode", "include") == "exclude":
        label = "Exclude " + label
    return label


def search_profiles(
    profiles: list[dict],
    catalog: list[dict],
    filters: list[dict],
    grouping: str = "and",
    category_grouping: dict[str, str] | None = None,
) -> list[dict]:
    """Required filters decide who appears. Preferred filters improve the score."""
    if grouping not in {"and", "or"}:
        raise ValueError("Grouping must be and or or.")
    category_grouping = category_grouping or {}
    if any(value not in {"and", "or"} for value in category_grouping.values()):
        raise ValueError("Category grouping must be and or or.")
    validate_constraints(filters, catalog)
    by_id = {item["id"]: item for item in catalog}
    results = []
    for profile in profiles:
        facts = {}
        for fact in profile.get("competencies", []) + profile.get("languages", []):
            facts[fact["filter_id"]] = fact

        matched = []
        unmet = []
        unknown = []
        required_groups = {}
        exclusions_pass = True
        matched_weight = 0.0
        total_weight = 0.0

        for constraint in filters:
            item = by_id[constraint["filter_id"]]
            satisfied = matches_filter(facts, constraint, item)
            excluded = constraint.get("mode", "include") == "exclude"
            required = constraint.get("requirement", "mandatory") == "mandatory"
            label = filter_label(constraint, item)

            # Missing information stays unknown, even for an exclusion.
            if excluded and satisfied is not None:
                satisfied = not satisfied
            if excluded:
                exclusions_pass = exclusions_pass and satisfied is True
            elif required:
                category_id = item["category_id"]
                required_groups.setdefault(category_id, []).append(satisfied is True)

            if satisfied is None:
                unknown.append(label)
            elif satisfied:
                matched.append(label)
            else:
                unmet.append(label)

            weight = 0.5
            if required or excluded:
                weight = 1.0
            total_weight += weight
            if satisfied is True:
                matched_weight += weight

        groups = []
        for category_id, values in required_groups.items():
            mode = category_grouping.get(category_id, grouping)
            groups.append(matches_group(values, mode))

        if not exclusions_pass or not matches_group(groups, grouping):
            continue

        score = 0.0
        if total_weight:
            score = round(100 * matched_weight / total_weight, 1)
        results.append({
            "profile": profile,
            "score": score,
            "matched": matched,
            "unmet": unmet,
            "unknown": unknown,
            "eligible": True,
        })

    # Best score first, then name and ID for a stable order.
    return sorted(results, key=lambda row: (
        -row["score"], row["profile"]["display_name"].casefold(), row["profile"]["id"],
    ))
