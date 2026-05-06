from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAFETY_POLICY_PATH = ROOT / "SAFETY_POLICY.md"


def load_safety_policy_markdown(path: Path | None = None) -> str:
    policy_path = path or SAFETY_POLICY_PATH
    return policy_path.read_text(encoding="utf-8")


def parse_safety_policy_markdown(markdown: str) -> dict:
    sections: dict[str, object] = {
        "scope": "",
        "must_not_generate": [],
        "must_include_on_every_export": [],
        "preflight_checks": [],
        "preflight_block_behavior": [],
        "mode_restrictions": {},
        "audit_requirements": [],
        "future_sequence_export_requirements": [],
        "alphafold_output_requirements": [],
        "agent_skill_requirements": [],
        "unsafe_text_scanner_checks": [],
    }

    current_section: str | None = None
    current_mode: str | None = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            current_mode = None
            current_section = {
                "scope": "scope",
                "hard boundaries": None,
                "safety preflight system": None,
                "mode restrictions": "mode_restrictions",
                "audit requirements": "audit_requirements",
                "mrna / construct handling": "future_sequence_export_requirements",
                "alphafold output policy": "alphafold_output_requirements",
                "agent skill safety": "agent_skill_requirements",
                "unsafe text scanner": "unsafe_text_scanner_checks",
            }.get(heading)
            continue
        if line.startswith("### "):
            subheading = line[4:].strip().lower()
            if subheading == "must not generate":
                current_section = "must_not_generate"
                current_mode = None
            elif subheading == "must include on every export":
                current_section = "must_include_on_every_export"
                current_mode = None
            elif subheading in {"demo mode", "dog / veterinary mode", "human / clinical mode"}:
                current_section = "mode_restrictions"
                current_mode = subheading
                sections["mode_restrictions"].setdefault(subheading, [])
            else:
                current_mode = None
            continue
        if line.startswith("The preflight system checks:"):
            current_section = "preflight_checks"
            continue
        if line.startswith("If the preflight system blocks an action:"):
            current_section = "preflight_block_behavior"
            continue
        if current_section == "scope" and not line.startswith("#"):
            sections["scope"] = f"{sections['scope']} {line}".strip()
            continue
        if line.startswith("- "):
            item = line[2:].strip()
            if current_section == "mode_restrictions" and current_mode:
                sections["mode_restrictions"][current_mode].append(item)
            elif current_section in sections and isinstance(sections[current_section], list):
                sections[current_section].append(item)
            continue
        if current_section == "must_not_generate" and line[0].isdigit():
            sections["must_not_generate"].append(line.split(". ", 1)[1] if ". " in line else line)
            continue

    return sections


def build_safety_policy_metrics(policy: dict) -> list[dict[str, str]]:
    return [
        {"label": "Blocked outputs", "value": str(len(policy.get("must_not_generate") or []))},
        {
            "label": "Export requirements",
            "value": str(len(policy.get("must_include_on_every_export") or [])),
        },
        {"label": "Preflight checks", "value": str(len(policy.get("preflight_checks") or []))},
        {"label": "Mode profiles", "value": str(len(policy.get("mode_restrictions") or {}))},
    ]


def format_safety_policy_summary(policy: dict) -> str:
    lines = []
    scope = policy.get("scope") or "No scope text loaded."
    lines.append(scope)
    lines.append("")
    lines.append(f"blocked_outputs={len(policy.get('must_not_generate') or [])}")
    lines.append(f"export_requirements={len(policy.get('must_include_on_every_export') or [])}")
    lines.append(f"preflight_checks={len(policy.get('preflight_checks') or [])}")
    mode_names = ", ".join(sorted((policy.get("mode_restrictions") or {}).keys())) or "none"
    lines.append(f"modes={mode_names}")
    return "\n".join(lines)


def build_mode_restriction_rows(policy: dict) -> list[dict[str, str]]:
    rows = []
    for mode_name, restrictions in (policy.get("mode_restrictions") or {}).items():
        rows.append(
            {
                "mode": mode_name,
                "restriction_count": str(len(restrictions)),
                "restrictions": " | ".join(restrictions),
            }
        )
    return rows


def derive_safety_policy_references(error_payload: dict, policy: dict) -> list[str]:
    payload = error_payload or {}
    text = " ".join(
        str(part).lower()
        for part in (
            payload.get("detail"),
            payload.get("safety_reason"),
            " ".join(payload.get("blocked_patterns") or []),
        )
        if part
    )

    refs: list[str] = []

    def add(section: str, item: str) -> None:
        ref = f"{section} -> {item}"
        if ref not in refs:
            refs.append(ref)

    if any(token in text for token in ("expert mode", "professional attestation")):
        for item in policy.get("preflight_checks") or []:
            lowered = item.lower()
            if "expert mode" in lowered or "professional attestation" in lowered:
                add("Safety Preflight System", item)
        for item in policy.get("future_sequence_export_requirements") or []:
            lowered = item.lower()
            if (
                "expert mode" in lowered
                or "approval checkpoint" in lowered
                or "attestation" in lowered
            ):
                add("mRNA / Construct Handling", item)

    if "external upload" in text:
        for item in policy.get("preflight_checks") or []:
            if "external data upload" in item.lower():
                add("Safety Preflight System", item)

    blocked_output_map = {
        "dose": "Dosing schedules for any substance",
        "dosing": "Dosing schedules for any substance",
        "inject": "Injection instructions of any kind",
        "injection": "Injection instructions of any kind",
        "formulation": "LNP formulation instructions",
        "manufactur": "DIY vaccine manufacturing protocols",
        "tumor": "Tumor-lysate preparation instructions",
        "lysate": "Tumor-lysate preparation instructions",
        "adjuvant": "Adjuvant mixing instructions",
        "sterility": "Sterility or QC release instructions for real administration",
        "qc": "Sterility or QC release instructions for real administration",
        "ready to inject": '"Ready to inject" sequence packages',
        "clinically valid": "Claims that AI or any model output is clinically valid without professional validation",
        "cure": "Claims that the system cures or treats cancer",
        "treat": "Claims that the system cures or treats cancer",
    }
    for needle, policy_text in blocked_output_map.items():
        if needle in text:
            add("Hard Boundaries / MUST NOT Generate", policy_text)

    scanner_map = {
        "dose": "Dosing language patterns",
        "dosing": "Dosing language patterns",
        "inject": "Injection/administration instructions",
        "injection": "Injection/administration instructions",
        "formulation": "Formulation recipes",
        "manufactur": "Manufacturing steps",
        "clinically valid": "Claims of clinical validity or cure",
        "cure": "Claims of clinical validity or cure",
        "treat": "Claims of clinical validity or cure",
    }
    for needle, policy_text in scanner_map.items():
        if needle in text:
            add("Unsafe Text Scanner", policy_text)

    if "sequence-level" in text:
        for item in policy.get("future_sequence_export_requirements") or []:
            add("mRNA / Construct Handling", item)

    if payload.get("safety_status") == "requires_approval":
        for item in policy.get("preflight_block_behavior") or []:
            if "logged" in item.lower() or "informed" in item.lower():
                add("Safety Preflight System", item)

    return refs
