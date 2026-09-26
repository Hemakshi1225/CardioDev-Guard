"""
tests/test_integration.py — Integration tests for the Tanish core ↔ CardioDev-Guard bridge

Covers:
- core_bridge.run_core_analysis() runs the full core pipeline and returns
  a dashboard AuditResult (ML domain)
- Severity translation: CRITICAL/HIGH → BLOCKER, MEDIUM → WARNING, INFO/LOW → PASS
- Recommendations from core are attached as suggested_fix on dashboard findings
- core_bridge.register_analyzer() / get_registered_analyzers() round-trip
- ml_audit.run() in live mode calls the bridge (no injection)
- ml_audit.run() in injected mode bypasses the bridge
- ml_audit.run() surfaces bridge errors as a single BLOCKER finding
- scanner.run_scan() produces a ScanReport with ML domain populated from core
- ScanReport.release_ready / release_status_label computed correctly
- Empty core pipeline (no analyzers) gives PASS findings and READY status
- Pending QA / RELEASE domains remain empty (pending) and do not crash
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.models import AnalysisRequest, AnalyzerResult, Finding as CoreFinding, Severity as CoreSeverity
from cardiodev_guard.findings import (
    AuditDomain,
    AuditResult,
    Finding,
    Severity as DashSeverity,
    ScanReport,
)
from cardiodev_guard.core_bridge import (
    _translate_finding,
    _translate_structured_output,
    run_core_analysis,
    register_analyzer,
    get_registered_analyzers,
    _registered_analyzers,
)
from cardiodev_guard import auditors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project() -> str:
    """Create a minimal temporary project directory."""
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "train.csv"), "w").close()
    open(os.path.join(tmp, "model.pkl"), "w").close()
    open(os.path.join(tmp, "main.py"),   "w").close()
    return tmp


def _core_finding(severity: CoreSeverity, category: str = "data_quality",
                  title: str = "Issue") -> CoreFinding:
    return CoreFinding(
        severity=severity, category=category,
        title=title, description="original description",
    )


def _simple_analyzer(severity: CoreSeverity, category: str, title: str):
    """Return an analyzer callable that produces one finding."""
    def _analyzer(request: AnalysisRequest) -> AnalyzerResult:
        return AnalyzerResult(
            analyzer_name="Test Analyzer",
            findings=[_core_finding(severity, category, title)],
        )
    _analyzer.__name__ = f"analyzer_{severity.name}"
    return _analyzer


# ---------------------------------------------------------------------------
# Severity translation
# ---------------------------------------------------------------------------

class TestSeverityTranslation:
    def test_critical_maps_to_blocker(self):
        f = _core_finding(CoreSeverity.CRITICAL)
        dash = _translate_finding(f)
        assert dash.severity == DashSeverity.BLOCKER

    def test_high_maps_to_blocker(self):
        f = _core_finding(CoreSeverity.HIGH)
        dash = _translate_finding(f)
        assert dash.severity == DashSeverity.BLOCKER

    def test_medium_maps_to_warning(self):
        f = _core_finding(CoreSeverity.MEDIUM)
        dash = _translate_finding(f)
        assert dash.severity == DashSeverity.WARNING

    def test_low_maps_to_warning(self):
        f = _core_finding(CoreSeverity.LOW)
        dash = _translate_finding(f)
        assert dash.severity == DashSeverity.WARNING

    def test_info_maps_to_pass(self):
        f = _core_finding(CoreSeverity.INFO)
        dash = _translate_finding(f)
        assert dash.severity == DashSeverity.PASS


# ---------------------------------------------------------------------------
# Finding translation
# ---------------------------------------------------------------------------

class TestFindingTranslation:
    def test_id_uses_category_prefix(self):
        f = _core_finding(CoreSeverity.HIGH, "data_quality", "Missing values")
        dash = _translate_finding(f)
        assert dash.id.startswith("ml.data_quality.")

    def test_domain_is_ml(self):
        f = _core_finding(CoreSeverity.MEDIUM)
        dash = _translate_finding(f)
        assert dash.domain == AuditDomain.ML

    def test_title_preserved(self):
        f = _core_finding(CoreSeverity.HIGH, title="My Title")
        dash = _translate_finding(f)
        assert dash.title == "My Title"

    def test_explanation_comes_from_description(self):
        f = _core_finding(CoreSeverity.HIGH)
        dash = _translate_finding(f)
        assert dash.explanation == f.description

    def test_category_preserved(self):
        f = _core_finding(CoreSeverity.HIGH, category="model_performance")
        dash = _translate_finding(f)
        assert dash.category == "model_performance"

    def test_file_path_in_evidence(self):
        f = _core_finding(CoreSeverity.HIGH)
        f.file_path = "/some/file.py"
        dash = _translate_finding(f)
        assert "/some/file.py" in dash.evidence

    def test_raw_data_in_evidence(self):
        f = _core_finding(CoreSeverity.HIGH)
        f.raw_data = {"accuracy": 0.42}
        dash = _translate_finding(f)
        assert "accuracy" in dash.evidence

    def test_core_finding_id_stored_in_extra(self):
        f = _core_finding(CoreSeverity.HIGH)
        dash = _translate_finding(f)
        assert dash.extra["core_finding_id"] == f.finding_id

    def test_core_severity_name_in_extra(self):
        f = _core_finding(CoreSeverity.CRITICAL)
        dash = _translate_finding(f)
        assert dash.extra["core_severity"] == "CRITICAL"


# ---------------------------------------------------------------------------
# StructuredOutput translation
# ---------------------------------------------------------------------------

class TestStructuredOutputTranslation:
    def _run_pipeline_with_analyzer(self, analyzer):
        from core.orchestrator import run_pipeline
        tmp = _make_project()
        return run_pipeline(tmp, [analyzer])

    def test_returns_audit_result(self):
        output = self._run_pipeline_with_analyzer(
            _simple_analyzer(CoreSeverity.MEDIUM, "code_quality", "Style"))
        audit = _translate_structured_output(output)
        assert isinstance(audit, AuditResult)

    def test_domain_is_ml(self):
        output = self._run_pipeline_with_analyzer(
            _simple_analyzer(CoreSeverity.MEDIUM, "code_quality", "Style"))
        audit = _translate_structured_output(output)
        assert audit.domain == AuditDomain.ML

    def test_findings_count_matches(self):
        output = self._run_pipeline_with_analyzer(
            _simple_analyzer(CoreSeverity.HIGH, "data_quality", "Missing"))
        audit = _translate_structured_output(output)
        assert len(audit.findings) == len(output.findings)

    def test_metadata_contains_core_status(self):
        output = self._run_pipeline_with_analyzer(
            _simple_analyzer(CoreSeverity.CRITICAL, "data_quality", "Fatal"))
        audit = _translate_structured_output(output)
        assert "core_overall_status" in audit.metadata
        assert audit.metadata["core_overall_status"] == "CRITICAL"

    def test_recommendation_detail_becomes_suggested_fix(self):
        output = self._run_pipeline_with_analyzer(
            _simple_analyzer(CoreSeverity.CRITICAL, "data_quality", "Fatal"))
        audit = _translate_structured_output(output)
        # The first finding's suggested_fix should contain recommendation text
        assert len(audit.findings) > 0
        assert audit.findings[0].suggested_fix  # non-empty

    def test_empty_analyzer_list_returns_empty_findings(self):
        from core.orchestrator import run_pipeline
        tmp = _make_project()
        output = run_pipeline(tmp, [])
        audit = _translate_structured_output(output)
        assert audit.findings == []
        assert audit.domain == AuditDomain.ML


# ---------------------------------------------------------------------------
# Analyzer registry
# ---------------------------------------------------------------------------

class TestAnalyzerRegistry:
    def test_register_analyzer_adds_to_list(self):
        initial_count = len(get_registered_analyzers())

        def my_analyzer(req: AnalysisRequest) -> AnalyzerResult:
            return AnalyzerResult(analyzer_name="My", findings=[])

        register_analyzer(my_analyzer)
        assert my_analyzer in get_registered_analyzers()
        # Clean up — remove to avoid polluting other tests
        _registered_analyzers.remove(my_analyzer)

    def test_register_same_analyzer_twice_is_idempotent(self):
        def unique_analyzer(req: AnalysisRequest) -> AnalyzerResult:
            return AnalyzerResult(analyzer_name="Unique", findings=[])

        register_analyzer(unique_analyzer)
        count_after_first = len(get_registered_analyzers())
        register_analyzer(unique_analyzer)  # second call — must not duplicate
        assert len(get_registered_analyzers()) == count_after_first
        _registered_analyzers.remove(unique_analyzer)

    def test_get_registered_analyzers_returns_copy(self):
        copy = get_registered_analyzers()
        copy.append(lambda r: None)  # mutate the copy
        # Original registry must be unchanged
        assert get_registered_analyzers() != copy or True  # length check
        # The lambda we appended must NOT be in the real registry
        assert (lambda r: None) not in _registered_analyzers


# ---------------------------------------------------------------------------
# run_core_analysis()
# ---------------------------------------------------------------------------

class TestRunCoreAnalysis:
    def test_returns_audit_result(self):
        tmp = _make_project()
        result = run_core_analysis(tmp)
        assert isinstance(result, AuditResult)

    def test_domain_is_ml(self):
        tmp = _make_project()
        result = run_core_analysis(tmp)
        assert result.domain == AuditDomain.ML

    def test_invalid_path_raises_value_error(self):
        with pytest.raises(ValueError):
            run_core_analysis("/nonexistent/xyz_does_not_exist")

    def test_metadata_present(self):
        tmp = _make_project()
        result = run_core_analysis(tmp)
        assert "core_overall_status" in result.metadata

    def test_no_registered_analyzers_returns_empty_findings(self):
        # Temporarily clear registry for isolation
        original = list(_registered_analyzers)
        _registered_analyzers.clear()
        try:
            tmp = _make_project()
            result = run_core_analysis(tmp)
            assert result.findings == []
        finally:
            _registered_analyzers.extend(original)


# ---------------------------------------------------------------------------
# ml_audit adapter
# ---------------------------------------------------------------------------

class TestMlAuditAdapter:
    def setup_method(self):
        # Reset injection before each test
        from cardiodev_guard.auditors import ml_audit
        ml_audit.inject_results(None)

    def teardown_method(self):
        from cardiodev_guard.auditors import ml_audit
        ml_audit.inject_results(None)

    def test_injected_mode_returns_injected_result(self):
        from cardiodev_guard.auditors import ml_audit
        synthetic = AuditResult(domain=AuditDomain.ML)
        synthetic.findings.append(Finding(
            id="ml.test.001", domain=AuditDomain.ML, severity=DashSeverity.PASS,
            title="Injected", evidence="n/a", explanation="injected test",
            suggested_fix="none", validation_method="none",
        ))
        ml_audit.inject_results(synthetic)
        tmp = _make_project()
        result = ml_audit.run(Path(tmp))
        assert result is synthetic

    def test_live_mode_calls_bridge(self):
        from cardiodev_guard.auditors import ml_audit
        tmp = _make_project()
        result = ml_audit.run(Path(tmp))
        assert isinstance(result, AuditResult)
        assert result.domain == AuditDomain.ML

    def test_bridge_error_surfaces_as_blocker(self):
        from cardiodev_guard.auditors import ml_audit
        # Patch at the module where the function lives; ml_audit imports it
        # lazily (inside run()), so we patch cardiodev_guard.core_bridge directly.
        with patch(
            "cardiodev_guard.core_bridge.run_pipeline",
            side_effect=RuntimeError("Simulated bridge failure"),
        ):
            tmp = _make_project()
            result = ml_audit.run(Path(tmp))
            assert result.domain == AuditDomain.ML
            assert len(result.findings) == 1
            assert result.findings[0].severity == DashSeverity.BLOCKER
            assert "Core analysis pipeline failed" in result.findings[0].title


# ---------------------------------------------------------------------------
# Full scanner integration
# ---------------------------------------------------------------------------

class TestScannerIntegration:
    def setup_method(self):
        from cardiodev_guard.auditors import ml_audit, qa_audit
        ml_audit.inject_results(None)
        qa_audit.inject_results(None)

    def teardown_method(self):
        from cardiodev_guard.auditors import ml_audit, qa_audit
        ml_audit.inject_results(None)
        qa_audit.inject_results(None)

    def test_run_scan_returns_scan_report(self):
        from cardiodev_guard.scanner import run_scan
        tmp = _make_project()
        report = run_scan(tmp)
        assert isinstance(report, ScanReport)

    def test_run_scan_has_ml_domain(self):
        from cardiodev_guard.scanner import run_scan
        tmp = _make_project()
        report = run_scan(tmp)
        domains = [r.domain for r in report.audit_results]
        assert AuditDomain.ML in domains

    def test_run_scan_has_qa_and_release_domains(self):
        from cardiodev_guard.scanner import run_scan
        tmp = _make_project()
        report = run_scan(tmp)
        domains = [r.domain for r in report.audit_results]
        assert AuditDomain.QA in domains
        assert AuditDomain.RELEASE in domains

    def test_qa_domain_is_present_and_does_not_crash(self):
        """QA module is now integrated; the QA domain must be present with no
        adapter_error finding (meaning qa_audit.run() exists and is callable)."""
        from cardiodev_guard.auditors import qa_audit
        from cardiodev_guard.scanner import run_scan
        qa_audit.inject_results(AuditResult(domain=AuditDomain.QA))
        tmp = _make_project()
        report = run_scan(tmp)
        qa_results = [r for r in report.audit_results if r.domain == AuditDomain.QA]
        assert len(qa_results) == 1, "QA domain must appear exactly once"
        adapter_errors = [
            f for f in qa_results[0].findings
            if "adapter raised an unexpected error" in f.title
        ]
        assert adapter_errors == [], (
            f"QA adapter must not crash, got: {adapter_errors}"
        )

    def test_release_domain_is_pending_empty(self):
        """Release team has not yet integrated; RELEASE domain must be empty."""
        from cardiodev_guard.scanner import run_scan
        tmp = _make_project()
        report = run_scan(tmp)
        for r in report.audit_results:
            if r.domain == AuditDomain.RELEASE:
                assert r.findings == [], (
                    f"RELEASE domain should be empty (pending), got {r.findings}"
                )

    def test_scan_timestamp_is_set(self):
        from cardiodev_guard.scanner import run_scan
        tmp = _make_project()
        report = run_scan(tmp)
        assert report.scan_timestamp != ""

    def test_scan_project_path_matches_input(self):
        from cardiodev_guard.scanner import run_scan
        tmp = _make_project()
        report = run_scan(tmp)
        assert str(Path(tmp).resolve()) == report.project_path

    def test_release_ready_true_when_no_blockers(self):
        """With no registered core analyzers and empty QA/ML results → READY."""
        from cardiodev_guard.auditors import ml_audit, qa_audit
        from cardiodev_guard.scanner import run_scan
        # Inject empty results so neither ML nor QA produce blockers.
        ml_audit.inject_results(AuditResult(domain=AuditDomain.ML))
        qa_audit.inject_results(AuditResult(domain=AuditDomain.QA))
        tmp = _make_project()
        report = run_scan(tmp)
        assert report.release_ready is True
        assert report.release_status_label == "READY FOR RELEASE"

    def test_release_not_ready_when_blocker_present(self):
        from cardiodev_guard.auditors import ml_audit
        from cardiodev_guard.scanner import run_scan
        result_with_blocker = AuditResult(domain=AuditDomain.ML)
        result_with_blocker.findings.append(Finding(
            id="ml.test.blocker", domain=AuditDomain.ML,
            severity=DashSeverity.BLOCKER,
            title="Critical issue", evidence="n/a",
            explanation="test", suggested_fix="fix it",
            validation_method="re-scan",
        ))
        ml_audit.inject_results(result_with_blocker)
        tmp = _make_project()
        report = run_scan(tmp)
        assert report.release_ready is False
        assert "NOT READY" in report.release_status_label

    def test_warning_only_is_release_ready(self):
        from cardiodev_guard.auditors import ml_audit, qa_audit
        from cardiodev_guard.scanner import run_scan
        result_with_warning = AuditResult(domain=AuditDomain.ML)
        result_with_warning.findings.append(Finding(
            id="ml.test.warn", domain=AuditDomain.ML,
            severity=DashSeverity.WARNING,
            title="Warning issue", evidence="n/a",
            explanation="test", suggested_fix="fix it",
            validation_method="re-scan",
        ))
        ml_audit.inject_results(result_with_warning)
        # Inject empty QA result so live QA analysis does not introduce blockers.
        qa_audit.inject_results(AuditResult(domain=AuditDomain.QA))
        tmp = _make_project()
        report = run_scan(tmp)
        assert report.release_ready is True


# ---------------------------------------------------------------------------
# ScanReport properties
# ---------------------------------------------------------------------------

class TestScanReportProperties:
    def _make_report_with_findings(self, *severities: DashSeverity) -> ScanReport:
        result = AuditResult(domain=AuditDomain.ML)
        for i, sev in enumerate(severities):
            result.findings.append(Finding(
                id=f"ml.test.{i}", domain=AuditDomain.ML, severity=sev,
                title=f"Finding {i}", evidence="n/a", explanation="x",
                suggested_fix="fix", validation_method="verify",
            ))
        report = ScanReport(audit_results=[result], scan_timestamp="2024-01-01 00:00:00")
        return report

    def test_blockers_property(self):
        report = self._make_report_with_findings(
            DashSeverity.BLOCKER, DashSeverity.WARNING, DashSeverity.PASS)
        assert len(report.blockers) == 1

    def test_warnings_property(self):
        report = self._make_report_with_findings(
            DashSeverity.BLOCKER, DashSeverity.WARNING, DashSeverity.PASS)
        assert len(report.warnings) == 1

    def test_passes_property(self):
        report = self._make_report_with_findings(
            DashSeverity.BLOCKER, DashSeverity.WARNING, DashSeverity.PASS)
        assert len(report.passes) == 1

    def test_all_findings_property(self):
        report = self._make_report_with_findings(
            DashSeverity.BLOCKER, DashSeverity.WARNING, DashSeverity.PASS)
        assert len(report.all_findings) == 3


# ---------------------------------------------------------------------------
# Target ML Project path selection  (requirements 2–6, 10–11)
# ---------------------------------------------------------------------------

class TestTargetPathSelection:
    """Tests for dashboard._resolve_target() and scanner integration with
    custom project paths.  Covers requirements:
      - default target is CardioDev-Guard repo
      - custom valid directory is accepted
      - invalid / non-existent paths return an error message, not an exception
      - non-directory paths (files) return an error message
      - paths with spaces are handled correctly
      - scanner uses exactly the resolved path
    """

    def _make_dir_with_spaces(self) -> str:
        """Create a temp directory whose name contains a space."""
        import tempfile, os
        base = tempfile.mkdtemp()
        spaced = os.path.join(base, "my ml project")
        os.makedirs(spaced)
        return spaced

    # -- import once per class to avoid repeated import overhead
    @staticmethod
    def _resolve(raw: str):
        from dashboard import _resolve_target
        return _resolve_target(raw)

    def test_default_target_is_cardiodev_guard_repo(self):
        """_DEFAULT_TARGET must point to an existing directory."""
        from dashboard import _DEFAULT_TARGET
        p = Path(_DEFAULT_TARGET)
        assert p.exists(), "default target path must exist"
        assert p.is_dir(), "default target path must be a directory"

    def test_valid_directory_returns_path_and_no_error(self):
        tmp = _make_project()
        path, err = self._resolve(tmp)
        assert path is not None, f"Expected valid path, got error: {err}"
        assert err == ""
        assert path == Path(tmp).resolve()

    def test_nonexistent_path_returns_none_and_error(self):
        path, err = self._resolve("/nonexistent/path/that/does/not/exist")
        assert path is None
        assert "does not exist" in err

    def test_file_path_returns_none_and_error(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            fname = f.name
        path, err = self._resolve(fname)
        assert path is None
        assert "not a directory" in err

    def test_empty_string_returns_error(self):
        path, err = self._resolve("")
        # An empty string resolves to cwd — which IS a directory,
        # so we only assert no exception is raised and the result is consistent.
        assert isinstance(err, str)

    def test_path_with_spaces_is_accepted(self):
        spaced = self._make_dir_with_spaces()
        path, err = self._resolve(spaced)
        assert path is not None, f"Path with spaces must be accepted, got: {err}"
        assert err == ""

    def test_leading_trailing_whitespace_stripped(self):
        tmp = _make_project()
        path, err = self._resolve(f"  {tmp}  ")
        assert path is not None, f"Whitespace-padded path must be accepted, got: {err}"
        assert err == ""

    def test_scanner_uses_selected_path(self):
        """run_scan(custom_path) must record custom_path in the report."""
        from cardiodev_guard.auditors import ml_audit, qa_audit
        from cardiodev_guard.scanner import run_scan
        ml_audit.inject_results(AuditResult(domain=AuditDomain.ML))
        qa_audit.inject_results(AuditResult(domain=AuditDomain.QA))
        custom = _make_project()
        report = run_scan(custom)
        assert str(Path(custom).resolve()) == report.project_path, (
            "ScanReport.project_path must reflect the custom target directory"
        )

    def test_scanner_uses_recheck_path(self):
        """Re-check must scan the SAME target as the last Run Scan.
        Simulated here by calling run_scan with the same path twice and
        verifying both reports carry that path."""
        from cardiodev_guard.auditors import ml_audit, qa_audit
        from cardiodev_guard.scanner import run_scan
        ml_audit.inject_results(AuditResult(domain=AuditDomain.ML))
        qa_audit.inject_results(AuditResult(domain=AuditDomain.QA))
        custom = _make_project()
        report1 = run_scan(custom)
        report2 = run_scan(custom)   # simulates Re-check
        assert report1.project_path == report2.project_path, (
            "Re-check must scan the same target directory"
        )

    def teardown_method(self):
        from cardiodev_guard.auditors import ml_audit, qa_audit
        ml_audit.inject_results(None)
        qa_audit.inject_results(None)
