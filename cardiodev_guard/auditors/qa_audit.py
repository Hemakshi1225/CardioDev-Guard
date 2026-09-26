"""
QA audit adapter for Vanshika's QA analyzers.

Dashboard-side contract (what this file owns):
  - run(project_path) -> AuditResult   called by scanner.py
  - register_qa_analyzers()            called once at dashboard startup

QA-team contract:
  - Analyzers are registered via register_qa_analyzers() and executed
    live through the shared core bridge when run() is called.
  - Optional: call inject_results(audit_result) to supply a pre-built
    AuditResult for tests or overrides.

Deduplication:
  _deduplicate_findings() groups findings that represent the same
  logical issue across multiple dataset copies (e.g. phase2/phase3).
  It preserves all affected file paths in the merged evidence so the
  user can see exactly which files were checked.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from collections import defaultdict

from cardiodev_guard.core_bridge import register_analyzer
from cardiodev_guard.findings import AuditDomain, AuditResult, Finding, Severity

from analyzers.qa_analyzers import (
    analyze_missing_values,
    analyze_duplicates,
    analyze_class_imbalance,
    analyze_model_metrics,
    analyze_leakage,
)

# Module-level slot for results injected by tests or override callers.
_injected: AuditResult | None = None

# File-extension pattern used to strip trailing filenames from finding titles.
# Matches common ML data/model file suffixes.
_FILE_SUFFIX_RE = re.compile(
    r"\s+(?:in|for)\s+[\w\-. ]+\.(?:csv|pkl|parquet|tsv|json|h5|joblib)$",
    re.IGNORECASE,
)


def _issue_stem(title: str) -> str:
    """Return the title with any trailing 'in <filename>' or 'for <filename>'
    stripped, producing a stable grouping key for the same logical issue
    across different files.

    Examples
    --------
    "Missing values detected in framingham_phase2.csv"
    → "Missing values detected"

    "Model evaluation failed for logistic_model.pkl"
    → "Model evaluation failed"

    "Class imbalance detected in TenYearCHD (15.2% minority)"
    → unchanged  (no file-extension suffix)
    """
    return _FILE_SUFFIX_RE.sub("", title).strip()


def _deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Group findings that represent the same logical issue across multiple
    files into a single deduplicated finding.

    Grouping key: (category, issue_stem)
    where issue_stem strips any trailing "in <file>" / "for <file>" from the title.

    Merge rules:
    - severity  → highest among the group
    - title     → "<stem> [N file(s)]" when N > 1, original title when N == 1
    - evidence  → all per-file evidence strings joined with newlines
    - explanation / suggested_fix / validation_method → from the highest-severity
      member (most informative) in the group
    - id        → first finding's id  (stable, traceable)
    - extra     → merged dict of all members

    Findings with unique stems (i.e. not repeated) are returned unchanged.
    """
    # Severity ordering for "highest" comparison
    _SEV_ORDER = {Severity.BLOCKER: 2, Severity.WARNING: 1, Severity.PASS: 0}

    # Group by (category, stem)
    groups: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for f in findings:
        stem = _issue_stem(f.title)
        groups[(f.category, stem)].append(f)

    deduplicated: list[Finding] = []
    for (category, stem), group in groups.items():
        if len(group) == 1:
            deduplicated.append(group[0])
            continue

        # Sort group so highest-severity member is first (used for narrative fields)
        group_sorted = sorted(group, key=lambda f: _SEV_ORDER.get(f.severity, 0), reverse=True)
        best = group_sorted[0]
        n = len(group)

        # Build merged evidence: list every file's individual evidence block
        evidence_parts = []
        for i, f in enumerate(group_sorted, 1):
            evidence_parts.append(f"[{i}/{n}] {f.evidence}")
        merged_evidence = "\n".join(evidence_parts)

        # Merged extra dict
        merged_extra: dict = {}
        for f in group:
            merged_extra.update(f.extra)
        merged_extra["deduplicated_from"] = n
        merged_extra["affected_files"] = [
            f.extra.get("raw_data", {}).get("file_path", "")
            for f in group
            if f.extra.get("raw_data", {}).get("file_path", "")
        ]

        merged_title = f"{stem} [{n} file(s)]" if n > 1 else best.title

        deduplicated.append(Finding(
            id=best.id,
            domain=best.domain,
            severity=best.severity,
            title=merged_title,
            evidence=merged_evidence,
            explanation=best.explanation,
            suggested_fix=best.suggested_fix,
            validation_method=best.validation_method,
            category=category,
            extra=merged_extra,
        ))

    # Preserve the original relative ordering (first occurrence of each group)
    order: dict[str, int] = {}
    for i, f in enumerate(findings):
        stem = _issue_stem(f.title)
        key = (f.category, stem)
        if key not in order:
            order[key] = i
    deduplicated.sort(key=lambda f: order.get((_issue_stem(f.title), f.category), 0)
                      if False else order.get((f.category, _issue_stem(f.title)), 0))

    return deduplicated


def inject_results(audit_result: AuditResult) -> None:
    """Override the live analysis with a pre-built AuditResult.

    Call with ``None`` to reset to live mode.
    """
    global _injected
    _injected = audit_result


def register_qa_analyzers() -> None:
    """Register all QA analyzers with the shared core pipeline.

    Safe to call multiple times — core_bridge.register_analyzer() is
    idempotent (guards against duplicate entries by identity).
    """
    register_analyzer(analyze_missing_values)
    register_analyzer(analyze_duplicates)
    register_analyzer(analyze_class_imbalance)
    register_analyzer(analyze_model_metrics)
    register_analyzer(analyze_leakage)


def run(project_path: Path) -> AuditResult:  # noqa: ARG001
    """Return the QA audit result for *project_path*.

    Priority order:
    1. Return the injected AuditResult if one was set via inject_results().
    2. Run the core pipeline via core_bridge.run_core_analysis() (which
       executes all registered analyzers, including the QA ones) and
       return a QA-domain AuditResult.
    3. On any error, return an AuditResult containing a single BLOCKER
       finding so the dashboard always receives a renderable result.
    """
    if _injected is not None:
        return _injected

    try:
        from cardiodev_guard.core_bridge import run_core_analysis
        result = run_core_analysis(project_path)
        # Re-tag the domain as QA so the dashboard renders it under the QA tab.
        result.domain = AuditDomain.QA
        for finding in result.findings:
            finding.domain = AuditDomain.QA
        # Deduplicate repeated findings from multiple dataset copies.
        result.findings = _deduplicate_findings(result.findings)
        return result
    except Exception as exc:
        print(
            f"[CardioDev-Guard] WARNING: QA core bridge raised an error: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        error_result = AuditResult(domain=AuditDomain.QA)
        error_result.findings.append(
            Finding(
                id="qa.core_bridge_error",
                domain=AuditDomain.QA,
                severity=Severity.BLOCKER,
                category="analyzer_failure",
                title="QA analysis pipeline failed to run",
                evidence=f"{type(exc).__name__}: {exc}",
                explanation=(
                    "The QA core pipeline raised an unexpected error. "
                    "QA audit results are unavailable. "
                    "Check the project path and that all QA analyzer dependencies "
                    "are installed."
                ),
                suggested_fix=(
                    "Review the error message above, verify the project path is "
                    "a valid directory, and re-run the scan."
                ),
                validation_method=(
                    "Scan completes without this BLOCKER finding in the QA domain."
                ),
            )
        )
        return error_result
