"""Find catalog names and aliases mentioned in the user's text."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """Normalize spacing and Unicode, preserving technical punctuation and digits."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def mention_spans(text: str, value: str) -> list[tuple[int, int]]:
    # Match the original text so evidence offsets always refer to the user state.
    # '+'/'#' are identifier characters: selecting C from C++ is a false positive.
    if not value.strip():
        return []
    pattern = r"(?<![\w+#])" + re.escape(value.strip()).replace(r"\ ", r"\s+") + r"(?![\w+#])"
    return [(m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE)]


def evidence_for(text: str, item: dict) -> tuple[str | None, tuple[int, int] | None]:
    for value in [item["label"], *item.get("aliases", [])]:
        spans = mention_spans(text, value)
        if spans:
            start, end = spans[0]
            return text[start:end], (start, end)
    return None, None


def retrieve(state: str, catalog: list[dict], current_filters: list[dict], budget: int = 30) -> list[dict]:
    """Check existing selections, exact names, and then overlapping words."""
    current_ids = {item["filter_id"] for item in current_filters}
    state_tokens = set(re.findall(r"[\w+#]+", normalize(state)))
    ranked = []
    explicit_ids = set()
    for item in catalog:
        evidence, _ = evidence_for(state, item)
        if evidence:
            explicit_ids.add(item["id"])
        names = [item["label"], *item.get("aliases", [])]
        tokens = set()
        for name in names:
            for token in re.findall(r"[\w+#]+", normalize(name)):
                if len(token) > 2:
                    tokens.add(token)
        overlap = len(tokens & state_tokens) / max(1, len(tokens))
        score = 100 if evidence else overlap
        if evidence or overlap or item["id"] in current_ids:
            ranked.append((item["id"] in current_ids, score, item))
    # Reevaluate all current selections. Reject an oversized snapshot rather than
    # dropping it silently from the question budget.
    if len(current_ids | explicit_ids) > budget:
        raise ValueError("Current selections and explicitly named filters exceed the candidate-filter budget. Reduce the selection or increase the backend budget.")
    def priority(candidate):
        already_selected, score, item = candidate
        # Existing selections first, then the strongest text match.
        return not already_selected, -score, item["id"]

    ranked.sort(key=priority)
    return [item for _, _, item in ranked[:budget]]
