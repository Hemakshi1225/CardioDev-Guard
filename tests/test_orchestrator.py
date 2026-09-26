"""
tests/test_orchestrator.py — Unit tests for core/orchestrator.py

Covers:
- Normal analyzer runs and StructuredOutput is returned
- Crashing analyzer does not stop the pipeline
- Failed analyzer produces AnalyzerResult(success=False) with error_message
- Findings are aggregated, explained, and recommendations generated
- timestamp is a non-empty ISO 8601 string
- summary is a non-empty string containing project name and status
- overall_status: CRITICAL, NEEDS_WORK, READY computed correctly
- StructuredOutput returned even when all analyzers fail
- Empty analyzer list returns READY with no findings
- Invalid path raises ValueError
"""

import os
import tempfile

import pytest

from core.orchestrator import run_pipeline
from core.models import (
    AnalysisRequest,
    AnalyzerResult,
    Finding,
    OverallStatus,
    Severity,
    StructuredOutput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project() -> str:
    """Create a temporary directory with a minimal fake project and return its path.
    Caller is responsible for cleanup (use as a fixture or context manager)."""
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "train.csv"), "w").close()
    open(os.path.join(tmp, "model.pkl"), "w").close()
    open(os.path.join(tmp, "main.py"),   "w").close()
    return tmp


def _finding(severity: Severity, category: str = "data_quality",
             title: str = "Issue") -> Finding:
    return Finding(severity=severity, category=category,
                   title=title, description="d")


def good_analyzer(request: AnalysisRequest) -> AnalyzerResult:
    return AnalyzerResult(
        analyzer_name="Good Analyzer",
        findings=[_finding(Severity.MEDIUM, "code_quality", "Long function")],
    )


def crashing_analyzer(request: AnalysisRequest) -> AnalyzerResult:
    raise RuntimeError("Simulated analyzer crash")


# ---------------------------------------------------------------------------
# Basic pipeline execution
# ---------------------------------------------------------------------------

class TestBasicPipeline:
    def test_returns_structured_output(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert isinstance(out, StructuredOutput)

    def test_project_name_matches_directory(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert out.project_name == os.path.basename(tmp)

    def test_timestamp_is_non_empty_string(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert isinstance(out.timestamp, str)
        assert len(out.timestamp) > 0

    def test_timestamp_looks_like_iso8601(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        # Basic structure: "YYYY-MM-DDTHH:MM:SS"
        assert "T" in out.timestamp
        assert "-" in out.timestamp

    def test_analysis_request_present(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert out.analysis_request is not None

    def test_empty_analyzer_list_returns_ready(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [])
        assert out.overall_status == OverallStatus.READY
        assert out.findings       == []
        assert out.recommendations == []

    def test_invalid_path_raises_value_error(self):
        with pytest.raises(ValueError):
            run_pipeline("/nonexistent/path/xyz_abc_123", [good_analyzer])


# ---------------------------------------------------------------------------
# Analyzer results
# ---------------------------------------------------------------------------

class TestAnalyzerResults:
    def test_successful_analyzer_recorded(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert len(out.analyzer_results) == 1
        assert out.analyzer_results[0].success is True
        assert out.analyzer_results[0].analyzer_name == "Good Analyzer"

    def test_crashing_analyzer_does_not_stop_pipeline(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [crashing_analyzer, good_analyzer])
        # Both results present
        assert len(out.analyzer_results) == 2
        # Pipeline still returned a full output
        assert isinstance(out, StructuredOutput)

    def test_crashing_analyzer_recorded_as_failed(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [crashing_analyzer])
        assert len(out.analyzer_results) == 1
        failed = out.analyzer_results[0]
        assert failed.success is False

    def test_failed_analyzer_result_has_error_message(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [crashing_analyzer])
        failed = out.analyzer_results[0]
        assert failed.error_message is not None
        assert "RuntimeError" in failed.error_message

    def test_all_analyzers_fail_still_returns_output(self):
        def fail1(req): raise ValueError("Fail 1")
        def fail2(req): raise TypeError("Fail 2")
        tmp = _make_project()
        out = run_pipeline(tmp, [fail1, fail2])
        assert isinstance(out, StructuredOutput)
        assert len(out.analyzer_results) == 2
        assert all(r.success is False for r in out.analyzer_results)


# ---------------------------------------------------------------------------
# Findings, explanations, recommendations
# ---------------------------------------------------------------------------

class TestFindingsAndRecommendations:
    def test_findings_present_after_successful_analyzer(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert len(out.findings) > 0

    def test_findings_sorted_critical_first(self):
        def multi_analyzer(req):
            return AnalyzerResult(
                analyzer_name="Multi",
                findings=[
                    _finding(Severity.LOW,      category="code_quality",   title="L"),
                    _finding(Severity.CRITICAL,  category="data_quality",   title="C"),
                    _finding(Severity.MEDIUM,    category="test_coverage",  title="M"),
                ],
            )
        tmp = _make_project()
        out = run_pipeline(tmp, [multi_analyzer])
        severities = [f.severity for f in out.findings]
        assert severities == sorted(severities, reverse=True)

    def test_descriptions_enriched_by_explainer(self):
        def known_category_analyzer(req):
            return AnalyzerResult(
                analyzer_name="A",
                findings=[_finding(Severity.HIGH, "data_quality", "Missing values")],
            )
        tmp = _make_project()
        out = run_pipeline(tmp, [known_category_analyzer])
        assert out.findings[0].description != "d"  # enriched by explainer

    def test_recommendations_generated(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert len(out.recommendations) == len(out.findings)

    def test_recommendations_sorted_by_priority(self):
        def two_findings(req):
            return AnalyzerResult(
                analyzer_name="A",
                findings=[
                    _finding(Severity.INFO,     category="documentation", title="I"),
                    _finding(Severity.CRITICAL, category="data_quality",  title="C"),
                ],
            )
        tmp = _make_project()
        out = run_pipeline(tmp, [two_findings])
        priorities = [r.priority for r in out.recommendations]
        assert priorities == sorted(priorities)

    def test_failed_analyzer_injects_critical_finding(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [crashing_analyzer])
        assert any(
            f.category == "analyzer_failure" and f.severity == Severity.CRITICAL
            for f in out.findings
        )


# ---------------------------------------------------------------------------
# Overall status computation
# ---------------------------------------------------------------------------

class TestOverallStatus:
    def test_critical_finding_gives_critical_status(self):
        def critical_a(req):
            return AnalyzerResult(analyzer_name="A",
                findings=[_finding(Severity.CRITICAL, "data_quality", "Fatal")])
        tmp = _make_project()
        out = run_pipeline(tmp, [critical_a])
        assert out.overall_status == OverallStatus.CRITICAL

    def test_high_finding_only_gives_needs_work(self):
        def high_a(req):
            return AnalyzerResult(analyzer_name="A",
                findings=[_finding(Severity.HIGH, "model_performance", "Bad acc")])
        tmp = _make_project()
        out = run_pipeline(tmp, [high_a])
        assert out.overall_status == OverallStatus.NEEDS_WORK

    def test_medium_or_lower_gives_ready(self):
        def low_a(req):
            return AnalyzerResult(analyzer_name="A",
                findings=[_finding(Severity.MEDIUM, "code_quality", "Style")])
        tmp = _make_project()
        out = run_pipeline(tmp, [low_a])
        assert out.overall_status == OverallStatus.READY

    def test_no_findings_gives_ready(self):
        def empty_a(req):
            return AnalyzerResult(analyzer_name="A", findings=[])
        tmp = _make_project()
        out = run_pipeline(tmp, [empty_a])
        assert out.overall_status == OverallStatus.READY

    def test_critical_overrides_high(self):
        def mixed_a(req):
            return AnalyzerResult(analyzer_name="A", findings=[
                _finding(Severity.HIGH,     category="data_quality",     title="H"),
                _finding(Severity.CRITICAL, category="model_performance", title="C"),
            ])
        tmp = _make_project()
        out = run_pipeline(tmp, [mixed_a])
        assert out.overall_status == OverallStatus.CRITICAL

    def test_crashing_analyzer_gives_critical_status(self):
        # A crashed analyzer injects a CRITICAL analyzer_failure finding
        tmp = _make_project()
        out = run_pipeline(tmp, [crashing_analyzer])
        assert out.overall_status == OverallStatus.CRITICAL


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_is_non_empty_string(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert isinstance(out.summary, str)
        assert len(out.summary) > 0

    def test_summary_contains_project_name(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert out.project_name in out.summary

    def test_summary_contains_overall_status(self):
        tmp = _make_project()
        out = run_pipeline(tmp, [good_analyzer])
        assert out.overall_status.value in out.summary

    def test_summary_present_even_when_all_analyzers_fail(self):
        def fail(req): raise RuntimeError("Boom")
        tmp = _make_project()
        out = run_pipeline(tmp, [fail])
        assert isinstance(out.summary, str)
        assert len(out.summary) > 0
