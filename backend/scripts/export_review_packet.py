"""Clinician review packet generator (spec 7): one command exports every rule, its
evidence, and its test cases to a readable Markdown packet for a gynecologist to
review and sign (human task H7). All rules ship clinically_validated=false until
sign-off; this packet is the review surface."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings

SIGNOFF_LINES = [
    "Reviewer name: ______________________________",
    "KMPDC registration no: ______________________",
    "Signature: ______________  Date: ____________",
]


def main() -> int:
    settings = get_settings()
    ontology = settings.ontology_dir
    out_path = Path(__file__).resolve().parents[2] / "docs" / "clinician-review-packet.md"
    lines: list[str] = [
        "# SISI Health — Clinician Review Packet (DRAFT RULES, NOT VALIDATED)",
        "",
        "Every rule below ships `clinically_validated: false` and must be signed off",
        "by a licensed Kenyan clinician before the app enables it for real users",
        "(non-negotiable 3). Review each rule, its evidence, and its test cases.",
        "",
        f"Generated: {__import__('datetime').datetime.now().isoformat()}",
        "",
    ]
    for rule_path in sorted((ontology / "rules").glob("*.json")):
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
        lines += [
            f"## Rule: {rule['id']} v{rule['version']}",
            "",
            f"- Condition indicator: `{rule['condition']}`",
            f"- Minimum age: {rule['min_age']}",
            f"- Red flag: {rule['red_flag']}",
            f"- Output band when matched: `{rule['output_band']}`",
            f"- Inputs: {', '.join(i['name'] for i in rule['inputs'])}",
            f"- Logic: `{json.dumps(rule['logic'], ensure_ascii=False)}`",
            "",
            "### Evidence",
            "",
        ]
        for ev in rule["evidence"]:
            lines.append(
                f"- [{ev.get('source_type')}] {ev['title']}"
                f"{' — ' + ev['organization'] if ev.get('organization') else ''}"
                f"{' (' + str(ev['year']) + ')' if ev.get('year') else ''}"
                f" {ev.get('url') or '(no URL — verify at review)'}"
            )
            if ev.get("note"):
                lines.append(f"  - Note: {ev['note']}")
        lines += ["", "### Changelog", ""]
        for entry in rule["changelog"]:
            lines.append(f"- {entry['version']}: {entry['note']}")
        lines += ["", "### Sign-off", "", *SIGNOFF_LINES, ""]

    golden = json.loads((ontology / "golden" / "cases.json").read_text(encoding="utf-8"))
    lines += ["# Golden test cases (the engine MUST pass every one)", ""]
    for case in golden["cases"]:
        lines.append(
            f"- `{case['id']}` — age {case['age']}, {case['diary_days']} diary days → "
            f"band `{case['expected_band']}`, indicators {case['expected_indicators']}"
        )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[review-packet] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
