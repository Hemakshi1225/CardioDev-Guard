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
"""

from __future__ import annotations

import sys
from pathlib import Path

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
