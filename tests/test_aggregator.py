"""
tests/test_aggregator.py — Unit tests for core/aggregator.py

Covers:
- Empty input returns []
- Severity sorting (CRITICAL first, INFO last)
- Duplicate deduplication by (category, title, file_path)
- Highest-severity duplicate is kept
- Different file_path = distinct findings
- Failed AnalyzerResult with error_message injects synthetic CRITICAL finding
- Failed AnalyzerResult without error_message injects no synthetic finding
- Findings from multiple analyzers are combined
- Successful and failed results both contribute findings
"""

import pytest

from core.aggregator import aggregate
from core.models import AnalyzerResult, Finding, Severity


def _finding(severity: Severity, category: str = "data_quality",
             title: str = "T", file_path: str | None = None) -> Finding:
    return Finding(severity=severity, category=category,
                   title=title, description="d", file_path=file_path)


# ---------------------------------------------------------------------------
# Empty / trivial input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_list_returns_empty(self):
        assert aggregate([]) == []

    def test_single_result_no_findings_returns_empty(self):
        result = AnalyzerResult(analyzer_name="A")
        assert aggregate([result]) == []


# ---------------------------------------------------------------------------
# Severity sorting
# ---------------------------------------------------------------------------

class TestSeveritySorting:
    def test_critical_comes_first(self):
        findings = [
            _finding(Severity.INFO,     category="documentation",   title="A"),
            _finding(Severity.CRITICAL, category="data_quality",    title="B"),
            _finding(Severity.LOW,      category="code_quality",    title="C"),
            _finding(Severity.HIGH,     category="dependency",      title="D"),
            _finding(Severity.MEDIUM,   category="test_coverage",   title="E"),
        ]
        result = AnalyzerResult(analyzer_name="A", findings=findings)
        out = aggregate([result])
        severities = [f.severity for f in out]
        assert severities == sorted(severities, reverse=True)
        assert out[0].severity  == Severity.CRITICAL
        assert out[-1].severity == Severity.INFO

    def test_single_finding_sorted_trivially(self):
        f = _finding(Severity.MEDIUM)
        result = AnalyzerResult(analyzer_name="A", findings=[f])
        out = aggregate([result])
        assert len(out) == 1
        assert out[0].severity == Severity.MEDIUM


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_exact_duplicate_collapsed_to_one(self):
        f1 = _finding(Severity.LOW,  title="Dup", file_path="a.py")
        f2 = _finding(Severity.LOW,  title="Dup", file_path="a.py")
        result = AnalyzerResult(analyzer_name="A", findings=[f1, f2])
        out = aggregate([result])
        assert len(out) == 1

    def test_highest_severity_kept_on_duplicate(self):
        low  = _finding(Severity.LOW,    title="Issue", file_path="x.py")
        high = _finding(Severity.HIGH,   title="Issue", file_path="x.py")
        med  = _finding(Severity.MEDIUM, title="Issue", file_path="x.py")
        r1 = AnalyzerResult(analyzer_name="A", findings=[low, med])
        r2 = AnalyzerResult(analyzer_name="B", findings=[high])
        out = aggregate([r1, r2])
        assert len(out) == 1
        assert out[0].severity == Severity.HIGH

    def test_different_file_path_not_duplicate(self):
        fa = _finding(Severity.HIGH, title="Issue", file_path="a.py")
        fb = _finding(Severity.HIGH, title="Issue", file_path="b.py")
        result = AnalyzerResult(analyzer_name="A", findings=[fa, fb])
        out = aggregate([result])
        assert len(out) == 2

    def test_none_file_path_distinct_from_named_file(self):
        fa = _finding(Severity.HIGH, title="Issue", file_path="a.py")
        fn = _finding(Severity.HIGH, title="Issue", file_path=None)
        result = AnalyzerResult(analyzer_name="A", findings=[fa, fn])
        out = aggregate([result])
        assert len(out) == 2

    def test_different_category_not_duplicate(self):
        f1 = _finding(Severity.HIGH, category="data_quality",   title="T", file_path="f.py")
        f2 = _finding(Severity.HIGH, category="code_quality",   title="T", file_path="f.py")
        result = AnalyzerResult(analyzer_name="A", findings=[f1, f2])
        out = aggregate([result])
        assert len(out) == 2

    def test_different_title_not_duplicate(self):
        f1 = _finding(Severity.HIGH, title="Issue A", file_path="f.py")
        f2 = _finding(Severity.HIGH, title="Issue B", file_path="f.py")
        result = AnalyzerResult(analyzer_name="A", findings=[f1, f2])
        out = aggregate([result])
        assert len(out) == 2


# ---------------------------------------------------------------------------
# Synthetic failure findings
# ---------------------------------------------------------------------------

class TestSyntheticFailureFindings:
    def test_failed_result_with_error_message_injects_critical_finding(self):
        failed = AnalyzerResult(
            analyzer_name="BadAnalyzer",
            success=False,
            error_message="Out of memory",
        )
        out = aggregate([failed])
        assert len(out) == 1
        assert out[0].severity  == Severity.CRITICAL
        assert out[0].category  == "analyzer_failure"
        assert "BadAnalyzer"    in out[0].title
        assert out[0].description == "Out of memory"

    def test_failed_result_without_error_message_injects_nothing(self):
        failed = AnalyzerResult(
            analyzer_name="Silent",
            success=False,
            error_message=None,
        )
        out = aggregate([failed])
        assert out == []

    def test_failed_result_real_findings_still_included(self):
        f = _finding(Severity.MEDIUM, category="code_quality", title="Long func")
        failed = AnalyzerResult(
            analyzer_name="A",
            findings=[f],
            success=False,
            error_message="Partial failure",
        )
        out = aggregate([failed])
        titles = {finding.title for finding in out}
        assert "Long func" in titles
        assert any(finding.category == "analyzer_failure" for finding in out)


# ---------------------------------------------------------------------------
# Multi-analyzer combination
# ---------------------------------------------------------------------------

class TestMultiAnalyzerCombination:
    def test_findings_from_two_analyzers_combined(self):
        f1 = _finding(Severity.HIGH,   category="data_quality",  title="Missing values")
        f2 = _finding(Severity.MEDIUM, category="test_coverage", title="Low coverage")
        r1 = AnalyzerResult(analyzer_name="A", findings=[f1])
        r2 = AnalyzerResult(analyzer_name="B", findings=[f2])
        out = aggregate([r1, r2])
        assert len(out) == 2
        titles = {f.title for f in out}
        assert "Missing values" in titles
        assert "Low coverage"   in titles

    def test_cross_analyzer_deduplication(self):
        shared_low  = _finding(Severity.LOW,      title="Shared", file_path="x.py")
        shared_crit = _finding(Severity.CRITICAL, title="Shared", file_path="x.py")
        unique      = _finding(Severity.MEDIUM,   title="Unique", file_path="y.py")
        r1 = AnalyzerResult(analyzer_name="A", findings=[shared_low, unique])
        r2 = AnalyzerResult(analyzer_name="B", findings=[shared_crit])
        out = aggregate([r1, r2])
        assert len(out) == 2
        shared = next(f for f in out if f.title == "Shared")
        assert shared.severity == Severity.CRITICAL

    def test_output_still_sorted_after_multi_analyzer(self):
        r1 = AnalyzerResult(analyzer_name="A",
                            findings=[_finding(Severity.LOW,      title="L")])
        r2 = AnalyzerResult(analyzer_name="B",
                            findings=[_finding(Severity.CRITICAL, title="C")])
        r3 = AnalyzerResult(analyzer_name="C",
                            findings=[_finding(Severity.MEDIUM,   title="M")])
        out = aggregate([r1, r2, r3])
        severities = [f.severity for f in out]
        assert severities == sorted(severities, reverse=True)
