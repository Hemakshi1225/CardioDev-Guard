"""
tests/test_missing_values.py — Unit tests for analyze_missing_values()

Covers:
- Clean CSV (no NaN) produces no findings
- CSV with one NaN produces one finding
- Finding category is "data_quality"
- Finding severity is HIGH for partial NaN, CRITICAL for entirely-null column
- affected_columns list is correct in raw_data
- missing_count value is correct in raw_data
- per_column counts are correct in raw_data
- file_path is set to the csv path
- analyzer_name is set
- success is True
- Multiple columns with NaN are all reported in one finding per file
- Empty data file (0 rows) with no NaN produces no finding
- Unreadable file produces a finding without raising an exception
"""

import os
import tempfile

import pandas as pd
import pytest

from core.models import AnalysisRequest, ProjectInput, Severity
from analyzers.qa_analyzers import analyze_missing_values


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_csv(df: pd.DataFrame, directory: str, name: str = "train.csv") -> str:
    path = os.path.join(directory, name)
    df.to_csv(path, index=False)
    return path


def _make_request(csv_path: str) -> AnalysisRequest:
    directory = os.path.dirname(csv_path)
    return AnalysisRequest(
        project_input=ProjectInput(path=directory, name="test_proj"),
        data_files=[csv_path],
    )


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp(tmp_path):
    return str(tmp_path)


# ── clean data ────────────────────────────────────────────────────────────────

class TestCleanData:
    def test_no_nan_no_finding(self, tmp):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings == []

    def test_success_is_true_on_clean(self, tmp):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.success is True

    def test_empty_dataframe_no_finding(self, tmp):
        df = pd.DataFrame({"a": pd.Series([], dtype=float), "b": pd.Series([], dtype=float)})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings == []

    def test_no_data_files_no_finding(self, tmp):
        request = AnalysisRequest(
            project_input=ProjectInput(path=tmp, name="proj"),
            data_files=[],
        )
        result = analyze_missing_values(request)
        assert result.findings == []


# ── one NaN in one column ─────────────────────────────────────────────────────

class TestOneNaN:
    def test_one_nan_produces_one_finding(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert len(result.findings) == 1

    def test_category_is_data_quality(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings[0].category == "data_quality"

    def test_severity_is_high_for_partial_nan(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings[0].severity == Severity.HIGH

    def test_affected_column_in_raw_data(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert "a" in result.findings[0].raw_data["affected_columns"]

    def test_missing_count_correct(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings[0].raw_data["missing_count"] == 1

    def test_per_column_count_correct(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings[0].raw_data["per_column"]["a"] == 1

    def test_file_path_set(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings[0].file_path == path

    def test_analyzer_name_set(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.analyzer_name != ""

    def test_success_is_true(self, tmp):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.success is True


# ── entirely-null column ───────────────────────────────────────────────────────

class TestAllNullColumn:
    def test_entirely_null_column_is_critical(self, tmp):
        df = pd.DataFrame({"a": [None, None, None], "b": [1, 2, 3]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert len(result.findings) == 1
        assert result.findings[0].severity == Severity.CRITICAL

    def test_entirely_null_cols_listed_in_raw_data(self, tmp):
        df = pd.DataFrame({"a": [None, None, None], "b": [1, 2, 3]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert "a" in result.findings[0].raw_data["entirely_null_cols"]

    def test_missing_count_is_all_rows(self, tmp):
        df = pd.DataFrame({"a": [None, None, None], "b": [1, 2, 3]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings[0].raw_data["missing_count"] == 3


# ── multiple columns with NaN ─────────────────────────────────────────────────

class TestMultiColumnNaN:
    def test_two_nan_cols_single_finding(self, tmp):
        df = pd.DataFrame({"a": [None, 2, None], "b": [4, None, 6], "c": [7, 8, 9]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        # One finding per file (not one per column)
        assert len(result.findings) == 1

    def test_both_columns_in_affected(self, tmp):
        df = pd.DataFrame({"a": [None, 2, None], "b": [4, None, 6], "c": [7, 8, 9]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        affected = result.findings[0].raw_data["affected_columns"]
        assert "a" in affected
        assert "b" in affected

    def test_total_missing_count_correct(self, tmp):
        # a has 2 NaN, b has 1 NaN → total 3
        df = pd.DataFrame({"a": [None, 2, None], "b": [4, None, 6], "c": [7, 8, 9]})
        path = _write_csv(df, tmp)
        result = analyze_missing_values(_make_request(path))
        assert result.findings[0].raw_data["missing_count"] == 3


# ── unreadable file ───────────────────────────────────────────────────────────

class TestUnreadableFile:
    def test_unreadable_file_produces_finding_not_exception(self, tmp):
        bad_path = os.path.join(tmp, "bad.csv")
        with open(bad_path, "w") as f:
            f.write("not,a,valid\ncsv\x00content\n\x00\n")
        # Corrupt file: analyzer must not raise
        request = AnalysisRequest(
            project_input=ProjectInput(path=tmp, name="proj"),
            data_files=[bad_path],
        )
        # If pandas manages to parse it, fine. If not, a finding is produced.
        # Either way, no exception is raised.
        result = analyze_missing_values(request)
        assert result.success is True

    def test_nonexistent_file_produces_finding_not_exception(self, tmp):
        request = AnalysisRequest(
            project_input=ProjectInput(path=tmp, name="proj"),
            data_files=[os.path.join(tmp, "nonexistent.csv")],
        )
        result = analyze_missing_values(request)
        assert len(result.findings) == 1
        assert result.findings[0].category == "data_quality"
        assert result.success is True
