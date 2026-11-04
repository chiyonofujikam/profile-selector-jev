"""Convert preserved taxonomy into a reviewable import file; never seed implicitly.

Run from the repository root:
    uv run --project backend python -m scripts.convert_legacy --output local-data/catalog-review.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


CATEGORY_LABELS = {
    "tool": "Tools & technologies",
    "environnement-domain": "Domains",
    "environnement-context": "Contexts",
    "domain-competence": "Competencies",
    "domain-speciality": "Specialties",
}


def stable_id(kind: str, *path: str) -> str:
    """Preserve distinctions between equal labels at different legacy paths."""
    digest = hashlib.sha256(json.dumps(path, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    return f"legacy-{kind}-{digest}"


def convert_catalog(source: dict[str, Any], provenance: str) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError("Legacy catalog must be a JSON object.")
    unknown = set(source) - set(CATEGORY_LABELS)
    if unknown:
        raise ValueError(f"Unrecognized legacy categories: {', '.join(sorted(unknown))}")
    categories: list[dict[str, Any]] = []
    filters: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for order, (key, values) in enumerate(source.items()):
        category_id = stable_id("category", key)
        categories.append({"id": category_id, "key": key, "label": CATEGORY_LABELS[key],
                           "description": "Preserved legacy taxonomy; review definitions before demonstration use.",
                           "order": order})
        groups = {"": values} if isinstance(values, list) else values
        if not isinstance(groups, dict):
            raise ValueError(f"Category {key!r} must contain a list or named groups.")
        for group, records in groups.items():
            if not isinstance(group, str) or not isinstance(records, list):
                raise ValueError(f"Invalid group in category {key!r}.")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError(f"Invalid record in {key}/{group}.")
                label = record.get("name")
                description = record.get("description", "")
                if not isinstance(label, str) or not label.strip() or not isinstance(description, str):
                    raise ValueError(f"Every record in {key}/{group} requires a name and text description.")
                # Keep Unicode and meaningful punctuation exactly. Encoding repairs need human review.
                identifier = stable_id("filter", key, group, label)
                value = {"id": identifier, "category_id": category_id, "label": label,
                         "description": description, "subcategory": group or None,
                         "aliases": [], "level_ids": [], "active": True,
                         "legacy_path": json.dumps([key, group, label], ensure_ascii=False)}
                if identifier in filters:
                    if filters[identifier] != value:
                        raise ValueError(f"Conflicting duplicate at {key}/{group}/{label}; review manually.")
                    duplicates += 1
                    continue
                filters[identifier] = value
    return {"version": 1, "provenance": provenance, "categories": categories, "levels": [],
            "filters": list(filters.values()), "profiles": [], "examples": [],
            "review_notes": ["Unreviewed legacy reference; no candidate records generated.",
                             "Level associations and multilingual aliases require explicit review.",
                             "Taxonomy group membership does not imply possession of any skill.",
                             f"Collapsed {duplicates} identical duplicate records at the same path."]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/values_with_context.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing review file.")
    args = parser.parse_args(argv)
    try:
        if args.source.resolve() == args.output.resolve():
            raise ValueError("Output must differ from the legacy source.")
        if args.output.exists() and not args.force:
            raise ValueError("Output already exists; choose another path or use --force.")
        raw = args.source.read_bytes()
        source = json.loads(raw.decode("utf-8-sig"))
        provenance = f"Legacy reference {args.source.as_posix()}; sha256={hashlib.sha256(raw).hexdigest()}"
        payload = convert_catalog(source, provenance)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(payload['filters'])} catalog records for review to {args.output}. No database changes.")
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(f"Conversion failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
