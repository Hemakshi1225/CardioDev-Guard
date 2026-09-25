"""
tests/test_qa_adapter.py — Unit tests for the QA-domain quality indicator path

Tests the injection contract between Vanshika's analyzers and the
CardioDev-Guard dashboard, using the actual interfaces from:
  cardiodev_guard/auditors/qa_audit.py
  cardiodev_guard/scanner.py
  cardiodev_guard/findings.py

Two layers are tested:

Layer 1 — qa_audit adapter isolation
  inject_results() / run() behaviour: injection, reset, path-independence,
  field preservation, empty default.

Layer 2 — full scanner quality indicators via QA domain
  run_scan() picks up injected QA findings; ScanReport.release_ready /
  release_status_label / blockers / warnings / passes reflect QA findings.

All inputs are in-memory AuditResult / Finding objects — no files needed.
The ml_audit adapter is also injected with an empty result to isolate
quality indicator logic to the QA domain.

Teardown: inject_results(None) is called after every test to prevent
state leakage between tests (module-level global in qa_audit).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from cardiodev_guard.auditors import ml_audit, qa_audit
from cardiodev_guard.findings import (
    AuditDomain,
    AuditResult,
    Finding,
    Severity,
    ScanReport,
)
from cardiodev_guard.scanner import run_scan


# ── helpers ──────────────────────────────────────────────────────────────────

def _qa_finding(severity: Severity, title: str = "QA issue", idx: int = 0) -> Finding:
    """Construct a minimal valid QA-domain dashboard Finding."""
    return Finding(
        id=f"qa.test.{idx:03d}",
        domain=AuditDomain.QA,
        severity=severity,
        title=title,
        evidence="synthetic evidence",
        explanation="synthetic explanation",
        suggested_fix="synthetic fix",
        validation_method="re-run scan",
        category="data_quality",
    )


def _empty_qa_result() -> AuditResult:
    return AuditResult(domain=AuditDomain.QA)


def _empty_ml_result() -> AuditResult:
    return AuditResult(domain=AuditDomain.ML)


@pytest.fixture(autouse=True)
def reset_injections():
    """Reset both qa_audit and ml_audit injections before and after every test."""
    qa_audit.inject_results(None)
    ml_audit.inject_results(None)
    yield
    qa_audit.inject_results(None)
    ml_audit.inject_results(None)


@pytest.fixture
def tmp_project(tmp_path):
    """Minimal project directory required by run_scan."""
    (tmp_path / "train.csv").touch()
    (tmp_path / "model.pkl").touch()
    (tmp_path / "main.py").touch()
    return str(tmp_path)


# ── Layer 1: qa_audit adapter isolation ──────────────────────────────────────

class TestQaAuditAdapter:

    # default (no injection) behaviour
    def test_run_without_injection_returns_qa_domain(self):
        result = qa_audit.run(Path("/tmp"))
        assert result.domain == AuditDomain.QA

    def test_run_without_injection_returns_empty_findings(self):
        result = qa_audit.run(Path("/tmp"))
        assert result.findings == []

    def test_run_without_injection_success_has_no_blockers(self):
        result = qa_audit.run(Path("/tmp"))
        assert result.blockers == []

    # injection round-trip
    def test_injected_result_returned_by_run(self):
        injected = _empty_qa_result()
        injected.findings.append(_qa_finding(Severity.BLOCKER))
        qa_audit.inject_results(injected)
        returned = qa_audit.run(Path("/tmp"))
        assert returned is injected

    def test_injected_findings_count_preserved(self):
        result = _empty_qa_result()
        result.findings.extend([
            _qa_finding(Severity.BLOCKER,  "B", 0),
            _qa_finding(Severity.WARNING,  "W", 1),
            _qa_finding(Severity.PASS,     "P", 2),
        ])
        qa_audit.inject_results(result)
        returned = qa_audit.run(Path("/tmp"))
        assert len(returned.findings) == 3

    def test_injected_severity_preserved(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.BLOCKER, "Critical QA"))
        qa_audit.inject_results(result)
        returned = qa_audit.run(Path("/tmp"))
        assert returned.findings[0].severity == Severity.BLOCKER

    def test_injected_title_preserved(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.WARNING, "Duplicate rows found"))
        qa_audit.inject_results(result)
        returned = qa_audit.run(Path("/tmp"))
        assert returned.findings[0].title == "Duplicate rows found"

    def test_injected_domain_is_qa(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.PASS, "All clean"))
        qa_audit.inject_results(result)
        returned = qa_audit.run(Path("/tmp"))
        assert returned.domain == AuditDomain.QA

    # reset behaviour
    def test_inject_none_resets_to_empty_result(self):
        qa_audit.inject_results(_empty_qa_result())
        qa_audit.inject_results(None)   # reset
        returned = qa_audit.run(Path("/tmp"))
        assert returned.findings == []

    def test_run_accepts_nonexistent_path_no_error(self):
        # qa_audit is a stub — it must not raise on a bad path
        result = qa_audit.run(Path("/this/does/not/exist"))
        assert isinstance(result, AuditResult)

    # AuditResult property methods
    def test_blockers_property_filters_correctly(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.BLOCKER, "B"))
        result.findings.append(_qa_finding(Severity.WARNING, "W"))
        assert len(result.blockers) == 1
        assert result.blockers[0].severity == Severity.BLOCKER

    def test_warnings_property_filters_correctly(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.BLOCKER, "B"))
        result.findings.append(_qa_finding(Severity.WARNING, "W"))
        assert len(result.warnings) == 1
        assert result.warnings[0].severity == Severity.WARNING

    def test_passes_property_filters_correctly(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.PASS, "P"))
        assert len(result.passes) == 1

    def test_is_ready_true_when_no_blockers(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.WARNING, "W"))
        assert result.is_ready is True

    def test_is_ready_false_when_blocker_present(self):
        result = _empty_qa_result()
        result.findings.append(_qa_finding(Severity.BLOCKER, "B"))
        assert result.is_ready is False


# ── Layer 2: scanner quality indicators via QA domain ────────────────────────

class TestScannerQualityIndicators:

    def test_run_scan_returns_scan_report(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        report = run_scan(tmp_project)
        assert isinstance(report, ScanReport)

    def test_scan_report_includes_qa_domain(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        report = run_scan(tmp_project)
        domains = [r.domain for r in report.audit_results]
        assert AuditDomain.QA in domains

    # release_ready with QA BLOCKER
    def test_qa_blocker_makes_report_not_release_ready(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.append(_qa_finding(Severity.BLOCKER, "Dup rows"))
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        assert report.release_ready is False

    def test_qa_blocker_release_status_label(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.append(_qa_finding(Severity.BLOCKER, "Dup rows"))
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        assert "NOT READY" in report.release_status_label

    # release_ready with QA WARNING only
    def test_qa_warning_only_is_release_ready(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.append(_qa_finding(Severity.WARNING, "Minor imbalance"))
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        assert report.release_ready is True

    def test_qa_warning_release_status_label(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.append(_qa_finding(Severity.WARNING, "Minor imbalance"))
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        assert report.release_status_label == "READY FOR RELEASE"

    # release_ready with empty QA (pending)
    def test_empty_qa_injection_is_release_ready(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_audit.inject_results(_empty_qa_result())
        report = run_scan(tmp_project)
        assert report.release_ready is True

    # ScanReport aggregate properties reflect QA findings
    def test_scan_report_blockers_includes_qa_blocker(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.append(_qa_finding(Severity.BLOCKER, "B"))
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        assert any(f.title == "B" for f in report.blockers)

    def test_scan_report_warnings_includes_qa_warning(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.append(_qa_finding(Severity.WARNING, "W"))
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        assert any(f.title == "W" for f in report.warnings)

    def test_scan_report_passes_includes_qa_pass(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.append(_qa_finding(Severity.PASS, "P"))
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        assert any(f.title == "P" for f in report.passes)

    def test_three_qa_findings_all_counted(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        qa_result = _empty_qa_result()
        qa_result.findings.extend([
            _qa_finding(Severity.BLOCKER, "B", 0),
            _qa_finding(Severity.WARNING, "W", 1),
            _qa_finding(Severity.PASS,    "P", 2),
        ])
        qa_audit.inject_results(qa_result)
        report = run_scan(tmp_project)
        qa_domain = next(r for r in report.audit_results if r.domain == AuditDomain.QA)
        assert len(qa_domain.findings) == 3

    def test_scan_timestamp_is_set(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        report = run_scan(tmp_project)
        assert report.scan_timestamp != ""

    def test_scan_project_path_matches_input(self, tmp_project):
        ml_audit.inject_results(_empty_ml_result())
        report = run_scan(tmp_project)
        assert report.project_path == str(Path(tmp_project).resolve())
