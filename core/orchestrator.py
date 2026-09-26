"""
core/orchestrator.py — End-to-end pipeline driver for CardioDev Guard
======================================================================

Public API
----------
::

    from core.orchestrator import run_pipeline

    output = run_pipeline("./my_ml_project", [my_analyzer])

This is the **single entry point** for the entire CardioDev Guard pipeline.
Pass the path to an ML project and a list of analyzer callables; receive
a fully populated :class:`~core.models.StructuredOutput` that UI, report,
and test modules can consume.

Pipeline stages
---------------
::

    project_path (str)
        └─> load_project()
                └─> AnalysisRequest
                        ├─> analyzer_1(AnalysisRequest) -> AnalyzerResult
                        ├─> analyzer_2(AnalysisRequest) -> AnalyzerResult  (errors caught)
                        └─> ...
                                └─> aggregate()
                                        └─> list[Finding]
                                                └─> explain()
                                                        └─> list[Finding]  (enriched)
                                                                └─> recommend()
                                                                        └─> list[Recommendation]
                                                                                └─> StructuredOutput

Analyzer contract
-----------------
Every analyzer callable registered by teammates must match this signature
exactly::

    def my_analyzer(request: AnalysisRequest) -> AnalyzerResult:
        ...

If an analyzer raises any unhandled exception, the orchestrator catches it,
prints a warning to ``stderr``, synthesises a failed
:class:`~core.models.AnalyzerResult`, and continues with the remaining
analyzers.  A complete :class:`~core.models.StructuredOutput` is always
returned — even when every analyzer fails.

Overall status rules
--------------------
=================  =====================================================
OverallStatus      Condition
=================  =====================================================
``CRITICAL``       At least one finding with ``Severity.CRITICAL``
``NEEDS_WORK``     No CRITICAL findings but at least one ``Severity.HIGH``
``READY``          No CRITICAL or HIGH findings
=================  =====================================================

Example
-------
::

    from core.orchestrator import run_pipeline
    from core.models import AnalysisRequest, AnalyzerResult

    def my_analyzer(request: AnalysisRequest) -> AnalyzerResult:
        # inspect request.model_files, request.data_files, etc.
        return AnalyzerResult(analyzer_name="My Analyzer", findings=[])

    output = run_pipeline("./my_ml_project", [my_analyzer])

    print(output.overall_status)    # OverallStatus.READY / NEEDS_WORK / CRITICAL
    print(output.summary)           # plain-English paragraph
    print(output.findings)          # list[Finding], CRITICAL first
    print(output.recommendations)   # list[Recommendation], priority 1 first
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from typing import Callable

from core.models import (
    AnalysisRequest,
    AnalyzerResult,
    OverallStatus,
    Severity,
    StructuredOutput,
)
from core.project_loader import load_project
from core.aggregator import aggregate
from core.explainer import explain
from core.recommender import recommend


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_pipeline(
    project_path: str,
    analyzers: list[Callable[[AnalysisRequest], AnalyzerResult]],
) -> StructuredOutput:
    """Run the full CardioDev Guard quality-analysis pipeline.

    Parameters
    ----------
    project_path:
        Absolute or relative filesystem path to the root of the ML project
        being analysed.  Passed directly to
        :func:`~core.project_loader.load_project`; raises :exc:`ValueError`
        if the path does not exist or is not a directory.
    analyzers:
        List of analyzer callables provided by teammates.  Each callable
        must accept one :class:`~core.models.AnalysisRequest` argument and
        return one :class:`~core.models.AnalyzerResult`.  An empty list is
        valid — the pipeline will return a ``READY`` output with no findings.

    Returns
    -------
    StructuredOutput
        Fully populated result object containing the aggregated findings,
        enriched descriptions, prioritised recommendations, overall status,
        and a plain-English summary.  Always returned, even when some or all
        analyzers fail.

    Raises
    ------
    ValueError
        If *project_path* does not exist or is not a directory (propagated
        from :func:`~core.project_loader.load_project`).
    """
    # ------------------------------------------------------------------
    # Stage 1 — Load project
    # ------------------------------------------------------------------
    analysis_request: AnalysisRequest = load_project(project_path)

    # ------------------------------------------------------------------
    # Stage 2 — Run analyzers, catching individual failures
    # ------------------------------------------------------------------
    analyzer_results: list[AnalyzerResult] = []

    for analyzer in analyzers:
        analyzer_name = getattr(analyzer, "__name__", repr(analyzer))
        try:
            result = analyzer(analysis_request)
        except Exception as exc:
            print(
                f"[CardioDev Guard] WARNING: analyzer '{analyzer_name}' raised an "
                f"unexpected exception and will be recorded as failed.\n"
                f"  {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            traceback.print_exc(file=sys.stderr)
            result = AnalyzerResult(
                analyzer_name=analyzer_name,
                findings=[],
                success=False,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        analyzer_results.append(result)

    # ------------------------------------------------------------------
    # Stage 3 — Aggregate findings from all results
    # ------------------------------------------------------------------
    findings = aggregate(analyzer_results)

    # ------------------------------------------------------------------
    # Stage 4 — Enrich finding descriptions
    # ------------------------------------------------------------------
    explain(findings)

    # ------------------------------------------------------------------
    # Stage 5 — Generate recommendations
    # ------------------------------------------------------------------
    recommendations = recommend(findings)

    # ------------------------------------------------------------------
    # Stage 6 — Compute overall status and summary, then package output
    # ------------------------------------------------------------------
    overall_status = _compute_status(findings)
    summary = _build_summary(
        project_name=analysis_request.project_input.name,
        n_analyzers=len(analyzers),
        findings=findings,
        n_recommendations=len(recommendations),
        overall_status=overall_status,
    )

    return StructuredOutput(
        project_name=analysis_request.project_input.name,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        analysis_request=analysis_request,
        analyzer_results=analyzer_results,
        findings=findings,
        recommendations=recommendations,
        overall_status=overall_status,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_status(findings: list) -> OverallStatus:
    """Derive :class:`~core.models.OverallStatus` from the aggregated findings.

    * Any ``CRITICAL`` finding  → ``OverallStatus.CRITICAL``
    * Any ``HIGH`` finding      → ``OverallStatus.NEEDS_WORK``
    * Otherwise                 → ``OverallStatus.READY``
    """
    has_critical = any(f.severity == Severity.CRITICAL for f in findings)
    if has_critical:
        return OverallStatus.CRITICAL

    has_high = any(f.severity == Severity.HIGH for f in findings)
    if has_high:
        return OverallStatus.NEEDS_WORK

    return OverallStatus.READY


def _build_summary(
    project_name: str,
    n_analyzers: int,
    findings: list,
    n_recommendations: int,
    overall_status: OverallStatus,
) -> str:
    """Build a plain-English one-paragraph summary of the pipeline run."""
    n_findings = len(findings)

    # Severity counts (only include non-zero ones to keep the summary concise)
    severity_counts: dict[str, int] = {}
    for f in findings:
        label = f.severity.name.capitalize()
        severity_counts[label] = severity_counts.get(label, 0) + 1

    # Build severity detail string, e.g. "2 Critical, 1 High, 3 Medium"
    severity_order = ["Critical", "High", "Medium", "Low", "Info"]
    severity_parts = [
        f"{severity_counts[s]} {s}"
        for s in severity_order
        if severity_counts.get(s, 0) > 0
    ]
    severity_detail = (
        " (" + ", ".join(severity_parts) + ")" if severity_parts else ""
    )

    analyzer_word = "analyzer" if n_analyzers == 1 else "analyzers"
    finding_word  = "issue"    if n_findings == 1  else "issues"
    rec_word      = "recommendation" if n_recommendations == 1 else "recommendations"

    return (
        f"CardioDev Guard analysed '{project_name}' using {n_analyzers} {analyzer_word} "
        f"and detected {n_findings} {finding_word}{severity_detail}. "
        f"{n_recommendations} {rec_word} were generated. "
        f"Overall release status: {overall_status.value}."
    )
