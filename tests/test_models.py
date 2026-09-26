"""
tests/test_models.py — Unit tests for core/models.py

Covers:
- Instantiation and defaults of every dataclass
- Severity ordering
- OverallStatus values
- Finding auto-generates unique finding_id
- dataclasses.asdict() serialization
"""

import dataclasses

import pytest

from core.models import (
    AnalysisRequest,
    AnalyzerResult,
    Finding,
    OverallStatus,
    ProjectInput,
    Recommendation,
    Severity,
    StructuredOutput,
)


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

class TestSeverity:
    def test_ordering_critical_is_highest(self):
        assert Severity.CRITICAL > Severity.HIGH

    def test_ordering_high_greater_than_medium(self):
        assert Severity.HIGH > Severity.MEDIUM

    def test_ordering_medium_greater_than_low(self):
        assert Severity.MEDIUM > Severity.LOW

    def test_ordering_low_greater_than_info(self):
        assert Severity.LOW > Severity.INFO

    def test_full_chain(self):
        order = [Severity.INFO, Severity.LOW, Severity.MEDIUM,
                 Severity.HIGH, Severity.CRITICAL]
        assert order == sorted(order)

    def test_numeric_values(self):
        assert Severity.INFO.value     == 1
        assert Severity.LOW.value      == 2
        assert Severity.MEDIUM.value   == 3
        assert Severity.HIGH.value     == 4
        assert Severity.CRITICAL.value == 5

    def test_sort_descending_gives_critical_first(self):
        findings_severities = [Severity.LOW, Severity.CRITICAL, Severity.MEDIUM]
        result = sorted(findings_severities, reverse=True)
        assert result[0] == Severity.CRITICAL


# ---------------------------------------------------------------------------
# OverallStatus
# ---------------------------------------------------------------------------

class TestOverallStatus:
    def test_ready_value(self):
        assert OverallStatus.READY.value == "READY"

    def test_needs_work_value(self):
        assert OverallStatus.NEEDS_WORK.value == "NEEDS_WORK"

    def test_critical_value(self):
        assert OverallStatus.CRITICAL.value == "CRITICAL"

    def test_all_three_members_exist(self):
        members = {s.value for s in OverallStatus}
        assert members == {"READY", "NEEDS_WORK", "CRITICAL"}


# ---------------------------------------------------------------------------
# ProjectInput
# ---------------------------------------------------------------------------

class TestProjectInput:
    def test_basic_instantiation(self):
        pi = ProjectInput(path="/tmp/proj", name="MyProj")
        assert pi.path == "/tmp/proj"
        assert pi.name == "MyProj"

    def test_metadata_defaults_to_empty_dict(self):
        pi = ProjectInput(path="/tmp/proj", name="MyProj")
        assert pi.metadata == {}

    def test_metadata_not_shared_between_instances(self):
        pi1 = ProjectInput(path="/a", name="A")
        pi2 = ProjectInput(path="/b", name="B")
        pi1.metadata["key"] = "val"
        assert pi2.metadata == {}

    def test_metadata_can_be_set(self):
        pi = ProjectInput(path="/p", name="P", metadata={"version": "1.0"})
        assert pi.metadata["version"] == "1.0"


# ---------------------------------------------------------------------------
# AnalysisRequest
# ---------------------------------------------------------------------------

class TestAnalysisRequest:
    def _make_pi(self):
        return ProjectInput(path="/tmp/proj", name="Proj")

    def test_all_file_lists_default_to_empty(self):
        ar = AnalysisRequest(project_input=self._make_pi())
        assert ar.model_files   == []
        assert ar.data_files    == []
        assert ar.test_files    == []
        assert ar.source_files  == []
        assert ar.doc_files     == []

    def test_file_lists_not_shared_between_instances(self):
        ar1 = AnalysisRequest(project_input=self._make_pi())
        ar2 = AnalysisRequest(project_input=self._make_pi())
        ar1.model_files.append("model.pkl")
        assert ar2.model_files == []

    def test_can_populate_file_lists(self):
        ar = AnalysisRequest(
            project_input=self._make_pi(),
            source_files=["main.py"],
            data_files=["train.csv"],
        )
        assert ar.source_files == ["main.py"]
        assert ar.data_files   == ["train.csv"]

    def test_project_input_stored(self):
        pi = self._make_pi()
        ar = AnalysisRequest(project_input=pi)
        assert ar.project_input is pi


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

class TestFinding:
    def test_basic_instantiation(self):
        f = Finding(severity=Severity.HIGH, category="data_quality",
                    title="Missing values", description="desc")
        assert f.severity    == Severity.HIGH
        assert f.category    == "data_quality"
        assert f.title       == "Missing values"
        assert f.description == "desc"

    def test_file_path_defaults_to_none(self):
        f = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        assert f.file_path is None

    def test_line_number_defaults_to_none(self):
        f = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        assert f.line_number is None

    def test_raw_data_defaults_to_empty_dict(self):
        f = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        assert f.raw_data == {}

    def test_finding_id_auto_generated(self):
        f = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        assert isinstance(f.finding_id, str)
        assert len(f.finding_id) == 36  # UUID4 format

    def test_each_finding_gets_unique_id(self):
        f1 = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        f2 = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        assert f1.finding_id != f2.finding_id

    def test_optional_fields_can_be_set(self):
        f = Finding(severity=Severity.HIGH, category="c", title="t", description="d",
                    file_path="train.py", line_number=42, raw_data={"x": 1})
        assert f.file_path   == "train.py"
        assert f.line_number == 42
        assert f.raw_data    == {"x": 1}


# ---------------------------------------------------------------------------
# AnalyzerResult
# ---------------------------------------------------------------------------

class TestAnalyzerResult:
    def test_basic_instantiation(self):
        ar = AnalyzerResult(analyzer_name="Test Analyzer")
        assert ar.analyzer_name == "Test Analyzer"

    def test_findings_default_to_empty_list(self):
        ar = AnalyzerResult(analyzer_name="A")
        assert ar.findings == []

    def test_success_defaults_to_true(self):
        ar = AnalyzerResult(analyzer_name="A")
        assert ar.success is True

    def test_error_message_defaults_to_none(self):
        ar = AnalyzerResult(analyzer_name="A")
        assert ar.error_message is None

    def test_failed_result(self):
        ar = AnalyzerResult(analyzer_name="A", success=False,
                            error_message="Something broke")
        assert ar.success is False
        assert ar.error_message == "Something broke"

    def test_findings_not_shared_between_instances(self):
        ar1 = AnalyzerResult(analyzer_name="A")
        ar2 = AnalyzerResult(analyzer_name="B")
        f = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        ar1.findings.append(f)
        assert ar2.findings == []


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

class TestRecommendation:
    def test_instantiation(self):
        rec = Recommendation(
            finding_id="abc-123",
            action_title="Fix it",
            detail="Do this now",
            priority=1,
        )
        assert rec.finding_id    == "abc-123"
        assert rec.action_title  == "Fix it"
        assert rec.detail        == "Do this now"
        assert rec.priority      == 1


# ---------------------------------------------------------------------------
# StructuredOutput
# ---------------------------------------------------------------------------

class TestStructuredOutput:
    def _make_ar(self):
        pi = ProjectInput(path="/p", name="P")
        return AnalysisRequest(project_input=pi)

    def test_basic_instantiation(self):
        out = StructuredOutput(
            project_name="Proj",
            timestamp="2024-01-01T00:00:00",
            analysis_request=self._make_ar(),
        )
        assert out.project_name == "Proj"
        assert out.timestamp    == "2024-01-01T00:00:00"

    def test_defaults(self):
        out = StructuredOutput(
            project_name="P",
            timestamp="2024-01-01T00:00:00",
            analysis_request=self._make_ar(),
        )
        assert out.analyzer_results == []
        assert out.findings         == []
        assert out.recommendations  == []
        assert out.overall_status   == OverallStatus.READY
        assert out.summary          == ""

    def test_lists_not_shared_between_instances(self):
        ar = self._make_ar()
        out1 = StructuredOutput(project_name="A", timestamp="t", analysis_request=ar)
        out2 = StructuredOutput(project_name="B", timestamp="t", analysis_request=ar)
        f = Finding(severity=Severity.LOW, category="c", title="t", description="d")
        out1.findings.append(f)
        assert out2.findings == []


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_asdict_produces_plain_dict(self):
        pi = ProjectInput(path="/p", name="P")
        ar = AnalysisRequest(project_input=pi)
        f  = Finding(severity=Severity.HIGH, category="data_quality",
                     title="T", description="D")
        rec = Recommendation(finding_id=f.finding_id,
                              action_title="Fix", detail="Now", priority=2)
        result = AnalyzerResult(analyzer_name="A", findings=[f])
        out = StructuredOutput(
            project_name="P",
            timestamp="2024-01-01T00:00:00",
            analysis_request=ar,
            analyzer_results=[result],
            findings=[f],
            recommendations=[rec],
            overall_status=OverallStatus.NEEDS_WORK,
            summary="summary text",
        )
        d = dataclasses.asdict(out)
        assert d["project_name"]   == "P"
        assert d["summary"]        == "summary text"
        assert isinstance(d["findings"][0]["severity"], int)  # IntEnum -> int
        assert len(d["findings"][0]["finding_id"]) == 36
