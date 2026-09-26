"""
Report Generator — CardioDev-Guard
=====================================
Converts a ScanReport into human-readable text and JSON formats.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from cardiodev_guard.findings import ScanReport, Severity


def to_json(report: ScanReport) -> str:
    """Serialize the full ScanReport to a JSON string."""
    data = {
        "scan_timestamp": report.scan_timestamp,
        "project_path": report.project_path,
        "release_ready": report.release_ready,
        "release_status_label": report.release_status_label,
        "summary": {
            "total": len(report.all_findings),
            "blockers": len(report.blockers),
            "warnings": len(report.warnings),
            "passes": len(report.passes),
        },
        "domains": [],
    }

    for result in report.audit_results:
        domain_data = {
            "domain": result.domain.value,
            "is_ready": result.is_ready,
            "findings": [],
        }
        for f in result.findings:
            domain_data["findings"].append({
                "id": f.id,
                "severity": f.severity.value,
                "category": f.category,
                "title": f.title,
                "evidence": f.evidence,
                "explanation": f.explanation,
                "suggested_fix": f.suggested_fix,
                "validation_method": f.validation_method,
            })
        data["domains"].append(domain_data)

    return json.dumps(data, indent=2)


def to_markdown(report: ScanReport) -> str:
    """Generate a Markdown-formatted report string."""
    lines = [
        "# CardioDev-Guard Audit Report",
        f"",
        f"**Scan time:** {report.scan_timestamp}  ",
        f"**Project:** `{report.project_path}`  ",
        f"**Release status:** {report.release_status_label}  ",
        f"",
        f"| Severity | Count |",
        f"|----------|-------|",
        f"| 🔴 BLOCKER | {len(report.blockers)} |",
        f"| 🟡 WARNING | {len(report.warnings)} |",
        f"| 🟢 PASS    | {len(report.passes)} |",
        f"",
    ]

    for result in report.audit_results:
        lines.append(f"## {result.domain.value} Audit")
        lines.append("")
        for f in result.findings:
            icon = {"BLOCKER": "🔴", "WARNING": "🟡", "PASS": "🟢"}.get(f.severity.value, "⚪")
            lines.append(f"### {icon} [{f.severity.value}] {f.title}")
            lines.append(f"")
            lines.append(f"- **Evidence:** {f.evidence}")
            lines.append(f"- **Explanation:** {f.explanation}")
            lines.append(f"- **Suggested fix:** {f.suggested_fix}")
            lines.append(f"- **Validation method:** {f.validation_method}")
            lines.append(f"")

    return "\n".join(lines)
