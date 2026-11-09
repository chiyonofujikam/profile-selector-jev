"""Load the supplied taxonomy and fictional engineering profiles for local demos.

Run: uv run --project backend python -m scripts.seed_demo
Add --write-only to generate the import JSON without touching PostgreSQL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from scripts.convert_legacy import convert_catalog, stable_id
from scripts.import_data import ImportPayload, main as import_data

ROOT = Path(__file__).resolve().parents[1]


def build_demo_data(data_dir: Path = ROOT / "data") -> dict:
    catalog_bytes = (data_dir / "values_with_context.json").read_bytes()
    source = json.loads(catalog_bytes.decode("utf-8-sig"))
    level_labels = json.loads((data_dir / "levels.json").read_text(encoding="utf-8-sig"))["tool-expertise"]
    provenance = (
        "Demo v1: filters copied from data/values_with_context.json "
        f"(sha256={hashlib.sha256(catalog_bytes).hexdigest()}). "
        "All profiles, skills, absences, and tool-level mappings are synthetic."
    )
    payload = convert_catalog(source, provenance)
    by_id = {item["id"]: item for item in payload["filters"]}
    levels = {label: f"demo-tool-{label}" for label in level_labels}
    payload["levels"] = [
        {"id": levels[label], "dimension": "tool-expertise", "label": label, "rank": rank}
        for rank, label in enumerate(level_labels, start=1)
    ]

    def fact(category: str, label: str, group: str = "", *, level: str | None = None, present: bool = True) -> dict:
        """Resolve an exact source path; never infer skills from a parent category."""
        identifier = stable_id("filter", category, group, label)
        if identifier not in by_id:
            raise ValueError(f"Demo filter is missing from the source: {category}/{group}/{label}")
        value = {"filter_id": identifier, "present": present}
        if level is not None:
            if category != "tool" or level not in levels or not present:
                raise ValueError(f"Unsupported demo tool level: {label}/{level}")
            by_id[identifier]["level_ids"] = list(levels.values())
            value["level_id"] = levels[level]
        return value

    # Each competency is explicitly listed. Names and career histories are fictional.
    payload["profiles"] = [
        {
            "id": "demo-alex", "display_name": "Alex Morgan (Demo)",
            "title": "Railway Signalling Engineer", "experience_years": 9,
            "summary": "Fictional engineer working on ERTMS requirements for main-line and high-speed rail. No metro projects in this demo record.",
            "competencies": [
                fact("tool", "DOORS", level="advanced"), fact("tool", "MATLAB", level="intermediate"),
                fact("tool", "EN50128"), fact("environnement-domain", "Railway"),
                fact("environnement-context", "High Speed Lines", "Railway"),
                fact("environnement-context", "Main Lines", "Railway"),
                fact("environnement-context", "Metro", "Railway", present=False),
                fact("domain-competence", "Signalling", "Railway"),
                fact("domain-speciality", "ERTMS", "Signalling"),
            ],
        },
        {
            "id": "demo-sam", "display_name": "Sam Laurent (Demo)",
            "title": "Metro Train Control Engineer", "experience_years": 7,
            "summary": "Fictional metro signalling specialist using CBTC, train detection, and requirements tooling.",
            "competencies": [
                fact("tool", "DOORS", level="intermediate"), fact("tool", "MATLAB", level="advanced"),
                fact("environnement-domain", "Railway"), fact("environnement-context", "Metro", "Railway"),
                fact("domain-competence", "Signalling", "Railway"),
                fact("domain-speciality", "CBTC", "Signalling"),
                fact("domain-speciality", "Train detection", "Signalling"),
            ],
        },
        {
            "id": "demo-jordan", "display_name": "Jordan Ellis (Demo)",
            "title": "Railway RAMS Engineer", "experience_years": 12,
            "summary": "Fictional safety and reliability specialist for main-line signalling. No metro projects in this demo record.",
            "competencies": [
                fact("tool", "DOORS", level="expert"), fact("tool", "RAM commander", level="advanced"),
                fact("tool", "EN50126"), fact("tool", "EN50129"), fact("tool", "AMDEC"),
                fact("environnement-domain", "Railway"), fact("environnement-context", "Main Lines", "Railway"),
                fact("environnement-context", "Metro", "Railway", present=False),
                fact("domain-competence", "Signalling", "Railway"),
            ],
        },
        {
            "id": "demo-morgan", "display_name": "Morgan Chen (Demo)",
            "title": "Rolling Stock Mechanical Engineer", "experience_years": 8,
            "summary": "Fictional engineer designing and simulating rail vehicle mechanical and braking systems.",
            "competencies": [
                fact("tool", "CATIA", level="advanced"), fact("tool", "SIMULINK", level="advanced"),
                fact("environnement-domain", "Railway"), fact("environnement-context", "Main Lines", "Railway"),
                fact("domain-competence", "Rolling Stock", "Railway"),
                fact("domain-speciality", "Mechanical Systems", "Rolling Stock"),
                fact("domain-speciality", "Braking Systems", "Rolling Stock"),
            ],
        },
        {
            "id": "demo-taylor", "display_name": "Taylor Martin (Demo)",
            "title": "Embedded Software Engineer", "experience_years": 6,
            "summary": "Fictional developer of embedded control and automation software for rolling stock.",
            "competencies": [
                fact("tool", "C++", level="advanced"), fact("tool", "Python", level="intermediate"),
                fact("tool", "GIT", level="advanced"), fact("tool", "VHDL", level="intermediate"),
                fact("environnement-domain", "Railway"), fact("domain-competence", "Rolling Stock", "Railway"),
                fact("domain-speciality", "Embedded systems", "Rolling Stock"),
                fact("domain-speciality", "Train Automation", "Rolling Stock"),
            ],
        },
        {
            "id": "demo-casey", "display_name": "Casey Dubois (Demo)",
            "title": "Electrical Design Engineer", "experience_years": 5,
            "summary": "Fictional engineer designing low-voltage installations and lighting for thermal energy facilities.",
            "competencies": [
                fact("tool", "CANECO BT", level="advanced"), fact("tool", "Dialux", level="intermediate"),
                fact("tool", "Autocad", level="advanced"), fact("environnement-domain", "Energy"),
                fact("environnement-context", "Thermal", "Energy"),
                fact("domain-competence", "Low Voltage", "Energy"),
                fact("domain-competence", "Transmission And Distribution", "Energy"),
                fact("domain-speciality", "Electrical Protection", "Transmission And Distribution"),
            ],
        },
        {
            "id": "demo-riley", "display_name": "Riley Haddad (Demo)",
            "title": "Energy Control Systems Engineer", "experience_years": 10,
            "summary": "Fictional renewable-energy controls specialist using MATLAB, SIMULINK, and Python.",
            "competencies": [
                fact("tool", "MATLAB", level="expert"), fact("tool", "SIMULINK", level="advanced"),
                fact("tool", "Python", level="advanced"), fact("environnement-domain", "Energy"),
                fact("environnement-context", "Renewable Energie", "Energy"),
                fact("domain-competence", "monitoring & control and instrumentation", "Energy"),
                fact("domain-speciality", "SNCC / Automatisme", "monitoring & control and instrumentation"),
                fact("domain-speciality", "Instrumentation", "monitoring & control and instrumentation"),
            ],
        },
        {
            "id": "demo-avery", "display_name": "Avery Bernard (Demo)",
            "title": "Nuclear Systems Safety Engineer", "experience_years": 11,
            "summary": "Fictional engineer managing equipment safety requirements in nuclear facilities.",
            "competencies": [
                fact("tool", "DOORS", level="advanced"), fact("tool", "IEC 61508"),
                fact("environnement-domain", "Energy"), fact("environnement-context", "Nucléaire", "Energy"),
                fact("domain-competence", "Equipment and facilities", "Energy"),
                fact("domain-speciality", "Pressure Equipment", "Equipment and facilities"),
            ],
        },
        {
            "id": "demo-quinn", "display_name": "Quinn Moreau (Demo)",
            "title": "Rail Infrastructure Design Engineer", "experience_years": 8,
            "summary": "Fictional civil infrastructure designer for high-speed railway projects.",
            "competencies": [
                fact("tool", "Autocad", level="expert"), fact("tool", "REVIT", level="advanced"),
                fact("tool", "BIM"), fact("environnement-domain", "Railway"),
                fact("environnement-context", "High Speed Lines", "Railway"),
                fact("domain-competence", "Infrastructure", "Railway"),
                fact("domain-speciality", "Fixed Installations / Civil Engineering", "Infrastructure"),
            ],
        },
        {
            "id": "demo-cameron", "display_name": "Cameron Idrissi (Demo)",
            "title": "Railway Telecommunications Engineer", "experience_years": 7,
            "summary": "Fictional metro communications engineer with industrial Ethernet and radio experience.",
            "competencies": [
                fact("tool", "Cisco"), fact("tool", "Hirschmann"), fact("tool", "Commutateurs Ethernet"),
                fact("environnement-domain", "Railway"), fact("environnement-context", "Metro", "Railway"),
                fact("domain-competence", "Low Voltage", "Railway"),
                fact("domain-speciality", "Radio / Wireless", "Low Voltage"),
                fact("domain-speciality", "Wired Transmissions", "Low Voltage"),
            ],
        },
        {
            "id": "demo-drew", "display_name": "Drew Patel (Demo)",
            "title": "Test Automation Engineer", "experience_years": 4,
            "summary": "Fictional engineer automating tests and data checks for renewable-energy control systems.",
            "competencies": [
                fact("tool", "Python", level="expert"), fact("tool", "GIT", level="advanced"),
                fact("tool", "TestLink", level="advanced"), fact("environnement-domain", "Energy"),
                fact("environnement-context", "Renewable Energie", "Energy"),
                fact("domain-competence", "Transmission And Distribution", "Energy"),
                fact("domain-speciality", "Digital Control Systems (DCS)", "Transmission And Distribution"),
            ],
        },
        {
            "id": "demo-robin", "display_name": "Robin Garcia (Demo)",
            "title": "Junior Railway Requirements Engineer", "experience_years": 2,
            "summary": "Fictional junior engineer learning ERTMS requirements and DOORS on main-line projects. No metro projects in this demo record.",
            "competencies": [
                fact("tool", "DOORS", level="basic"), fact("tool", "MATLAB", level="basic"),
                fact("environnement-domain", "Railway"), fact("environnement-context", "Main Lines", "Railway"),
                fact("environnement-context", "Metro", "Railway", present=False),
                fact("domain-competence", "Signalling", "Railway"),
                fact("domain-speciality", "ERTMS", "Signalling"),
            ],
        },
    ]
    payload["examples"] = [
        {"id": "demo-example-railway", "label": "Railway requirements", "state_text": "Railway and DOORS"},
        {"id": "demo-example-level", "label": "Advanced DOORS", "state_text": "DOORS advanced or higher"},
        {"id": "demo-example-exclusion", "label": "Railway without metro", "state_text": "Railway and DOORS, excluding Metro"},
        {"id": "demo-example-energy", "label": "Energy automation", "state_text": "Energy and Python"},
        {"id": "demo-example-mechanical", "label": "Rail mechanical design", "state_text": "Railway and CATIA"},
    ]
    payload["review_notes"] = [
        "User-requested demo data. Profiles and sample requirements are fictional, not accuracy evaluation data.",
        "Original filter labels, descriptions, paths, and converter IDs are preserved.",
        "Identical source entries at the same path collapse; different paths remain separate filters.",
        "Tool level labels and ascending order come from data/levels.json; applicability is a demo choice.",
        "Only explicitly listed skills are attached to profiles. Missing facts remain unknown.",
        "Metro absence is explicitly fictional on three railway profiles to demonstrate exclusions.",
        "No language filters are added because the supplied taxonomy has none.",
    ]
    ImportPayload.model_validate(payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "local-data/demo.json")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write-only", action="store_true", help="Generate JSON without contacting PostgreSQL.")
    mode.add_argument("--dry-run", action="store_true", help="Check the database import, then roll back.")
    args = parser.parse_args(argv)
    try:
        if args.output.resolve() in {(ROOT / "data" / name).resolve() for name in ("values_with_context.json", "levels.json")}:
            raise ValueError("Demo output must not overwrite the source taxonomy or levels.")
        payload = build_demo_data()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Prepared {len(payload['filters'])} filters and {len(payload['profiles'])} fictional profiles: {args.output}", flush=True)
        if args.write_only:
            return 0
        return import_data([str(args.output), *(["--dry-run"] if args.dry_run else [])])
    except (OSError, ValueError) as error:
        print(f"Demo setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
