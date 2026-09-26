"""
cardiodev_guard/core_bridge.py — Tanish core → CardioDev-Guard bridge
======================================================================

This module connects the existing Tanish core pipeline
(core.orchestrator.run_pipeline) to the CardioDev-Guard unified
finding format (cardiodev_guard.findings).

It does NOT duplicate or rewrite any core logic.  It only:

1. Calls ``core.orchestrator.run_pipeline()`` with the project path
   and whatever analyzers are registered.
2. Translates the resulting ``core.models.StructuredOutput`` into a
   ``cardiodev_guard.findings.AuditResult`` (ML domain) using the
   CardioDev-Guard Finding schema.
3. Exposes the translation so ``ml_audit.run()`` can call it directly.

Severity mapping
----------------
``core.models.Severity`` uses a five-level scale (INFO→CRITICAL).
``cardiodev_guard.findings.Severity`` uses three levels
(PASS / WARNING / BLOCKER).  The mapping is:

=================  ==================
core Severity      dashboard Severity
=================  ==================
CRITICAL           BLOCKER
HIGH               BLOCKER
MEDIUM             WARNING
LOW                WARNING
INFO               PASS
=================  ==================

Analyzer registration
---------------------
ML-domain analyzers (callable conforming to the core analyzer contract)
can be registered once by calling ``register_analyzer(fn)``.
The bridge holds a module-level list; ``run_core_analysis()`` passes
the full list to ``run_pipeline`` on every call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.models import (
    AnalysisRequest,
    AnalyzerResult,
    StructuredOutput,
    Severity as CoreSeverity,
)
from core.orchestrator import run_pipeline

from cardiodev_guard.findings import (
    AuditDomain,
    AuditResult,
    Finding,
    Severity as DashSeverity,
)


# ---------------------------------------------------------------------------
# Severity translation
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[CoreSeverity, DashSeverity] = {
    CoreSeverity.CRITICAL: DashSeverity.BLOCKER,
    CoreSeverity.HIGH:     DashSeverity.BLOCKER,
    CoreSeverity.MEDIUM:   DashSeverity.WARNING,
    CoreSeverity.LOW:      DashSeverity.WARNING,
    CoreSeverity.INFO:     DashSeverity.PASS,
}


# ---------------------------------------------------------------------------
# Analyzer registry
# ---------------------------------------------------------------------------

_registered_analyzers: list[Callable[[AnalysisRequest], AnalyzerResult]] = []


def register_analyzer(
    fn: Callable[[AnalysisRequest], AnalyzerResult],
) -> None:
    """Register a core-contract analyzer to run during ``run_core_analysis()``.

    Parameters
    ----------
    fn:
        Any callable matching ``(AnalysisRequest) -> AnalyzerResult``.
        Register once at import-time; the list persists for the
        lifetime of the process.
    """
    if fn not in _registered_analyzers:
        _registered_analyzers.append(fn)


def get_registered_analyzers() -> list[Callable[[AnalysisRequest], AnalyzerResult]]:
    """Return the current list of registered analyzers (read-only copy)."""
    return list(_registered_analyzers)


# ---------------------------------------------------------------------------
# Translation helpers
# ---------------------------------------------------------------------------

def _translate_finding(core_finding) -> Finding:
    """Convert one ``core.models.Finding`` to a ``cardiodev_guard.findings.Finding``.

    Evidence is taken from ``raw_data`` when available, falling back to
    the file-path / line-number the core analyzer recorded.  Explanation
    is the enriched description produced by ``core.explainer.explain()``.
    The recommendation ``detail`` is attached as the suggested fix via
    the ``extra`` payload so callers can access it if desired.
    """
    dash_severity = _SEVERITY_MAP.get(core_finding.severity, DashSeverity.WARNING)

    # Build evidence string from core finding attributes
    evidence_parts = []
    if core_finding.file_path:
        evidence_parts.append(f"File: {core_finding.file_path}")
    if core_finding.line_number:
        evidence_parts.append(f"Line: {core_finding.line_number}")
    if core_finding.raw_data:
        for k, v in core_finding.raw_data.items():
            evidence_parts.append(f"{k}: {v}")
    evidence = "; ".join(evidence_parts) if evidence_parts else "See finding description."

    return Finding(
        id=f"ml.{core_finding.category}.{core_finding.finding_id[:8]}",
        domain=AuditDomain.ML,
        severity=dash_severity,
        title=core_finding.title,
        evidence=evidence,
        explanation=core_finding.description,
        suggested_fix=(
            "See the ML audit recommendation for this finding. "
            "Re-run the scan after applying the fix."
        ),
        validation_method=(
            "Re-run the scan and confirm this finding no longer appears, "
            "or has been downgraded to PASS."
        ),
        category=core_finding.category,
        extra={
            "core_finding_id": core_finding.finding_id,
            "core_severity": core_finding.severity.name,
            "raw_data": core_finding.raw_data,
        },
    )


def _translate_structured_output(output: StructuredOutput) -> AuditResult:
    """Convert a full ``StructuredOutput`` to a dashboard ``AuditResult``.

    The overall status from the core pipeline is stored in ``metadata``
    so the dashboard can surface it alongside the per-domain findings.

    Recommendations produced by ``core.recommender`` are attached to
    their corresponding findings via ``extra["recommendation"]``.
    """
    # Build a lookup: finding_id → recommendation
    rec_by_finding: dict[str, str] = {
        r.finding_id: r.detail for r in output.recommendations
    }

    audit_result = AuditResult(
        domain=AuditDomain.ML,
        metadata={
            "core_overall_status": output.overall_status.value,
            "core_summary": output.summary,
            "core_timestamp": output.timestamp,
            "core_project_name": output.project_name,
            "analyzer_results": [
                {
                    "name": r.analyzer_name,
                    "success": r.success,
                    "error_message": r.error_message,
                    "finding_count": len(r.findings),
                }
                for r in output.analyzer_results
            ],
        },
    )

    for core_finding in output.findings:
        dash_finding = _translate_finding(core_finding)

        # Attach recommendation detail as the suggested_fix when available
        rec_detail = rec_by_finding.get(core_finding.finding_id)
        if rec_detail:
            dash_finding.suggested_fix = rec_detail
            dash_finding.extra["recommendation"] = rec_detail

        audit_result.findings.append(dash_finding)

    return audit_result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_core_analysis(project_path: str | Path) -> AuditResult:
    """Run the full Tanish core pipeline and return a dashboard AuditResult.

    Parameters
    ----------
    project_path:
        Path to the project root.  Passed directly to
        ``core.orchestrator.run_pipeline()``.

    Returns
    -------
    AuditResult
        ML-domain audit result containing translated findings from every
        registered core analyzer.  If no analyzers are registered, the
        core pipeline runs with an empty analyzer list (returns READY
        with no findings).

    Raises
    ------
    ValueError
        If *project_path* does not exist or is not a directory
        (propagated from ``core.project_loader.load_project()``).
    """
    project_path = str(Path(project_path).resolve())
    structured_output = run_pipeline(project_path, list(_registered_analyzers))
    return _translate_structured_output(structured_output)
