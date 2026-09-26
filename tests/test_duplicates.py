"""
tests/test_duplicates.py ΓÇö Unit tests for analyze_duplicates()

Covers:
- Clean CSV (all rows unique) produces no findings
- CSV with one duplicate pair produces one finding
- Finding category is "data_quality"
- Finding severity is HIGH for moderate duplicates, CRITICAL when >= 50%
- duplicate_count in raw_data is correct
- total_rows in raw_data is correct
- duplicate_fraction in raw_data is correct
- file_path is set to the csv path
- analyzer_name is set
- success is True
- All-duplicate dataset is CRITICAL severity
- Single-row CSV cannot have duplicates
- Unreadable / nonexistent file produces a finding, not an exception
"""

import os

import pandas as pd
import pytest

from core.models import AnalysisRequest, ProjectInput, Severity
from analyzers.qa_analyzers import analyze_duplicates


# ΓöÇΓöÇ helpers ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def _write_csv(df: pd.DataFrame, directory: str, name: str = "train.csv") -> str:
    path = os.path.join(directory, name)
    df.to_csv(path, index=False)
    return path


def _make_request(csv_path: str) -> AnalysisRequest:
    return AnalysisRequest(
        project_input=ProjectInput(path=os.path.dirname(csv_path), name="proj"),
        data_files=[csv_path],
    )


# ΓöÇΓöÇ clean data ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class TestCleanData:
    def test_no_duplicates_no_finding(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings == []

    def test_success_true_on_clean(self, tmp_path):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.success is True

    def test_single_row_no_finding(self, tmp_path):
        df = pd.DataFrame({"x": [42], "y": [99]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings == []

    def test_no_data_files_no_finding(self, tmp_path):
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            data_files=[],
        )
        result = analyze_duplicates(request)
        assert result.findings == []


# ΓöÇΓöÇ one duplicate pair ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# df_one_dup: rows 0 and 1 are identical ΓåÆ 1 duplicate (pandas counts
# the second occurrence), row 2 is unique

class TestOneDuplicate:
    def test_one_dup_produces_one_finding(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert len(result.findings) == 1

    def test_category_is_data_quality(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].category == "data_quality"

    def test_severity_is_high(self, tmp_path):
        # 1/3 = 33% duplicates ΓåÆ HIGH (< 50%)
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].severity == Severity.HIGH

    def test_duplicate_count_correct(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].raw_data["duplicate_count"] == 1

    def test_total_rows_correct(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].raw_data["total_rows"] == 3

    def test_duplicate_fraction_correct(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        # 1 dup out of 3 rows = 0.3333
        assert abs(result.findings[0].raw_data["duplicate_fraction"] - (1 / 3)) < 0.001

    def test_file_path_set(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].file_path == path

    def test_analyzer_name_set(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.analyzer_name != ""

    def test_success_true(self, tmp_path):
        df = pd.DataFrame({"x": [1, 1, 2], "y": [4, 4, 5]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.success is True


# ΓöÇΓöÇ all-duplicate dataset ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# df_all_dups: 3 identical rows ΓåÆ 2 duplicates, fraction = 2/3 Γëê 0.667 ΓåÆ CRITICAL

class TestAllDuplicates:
    def test_all_dups_produces_one_finding(self, tmp_path):
        df = pd.DataFrame({"x": [7, 7, 7], "y": [8, 8, 8]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert len(result.findings) == 1

    def test_all_dups_severity_critical(self, tmp_path):
        # 2 duplicates out of 3 rows = 66.7% >= 50% threshold ΓåÆ CRITICAL
        df = pd.DataFrame({"x": [7, 7, 7], "y": [8, 8, 8]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].severity == Severity.CRITICAL

    def test_all_dups_duplicate_count_correct(self, tmp_path):
        df = pd.DataFrame({"x": [7, 7, 7], "y": [8, 8, 8]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].raw_data["duplicate_count"] == 2

    def test_all_dups_total_rows_correct(self, tmp_path):
        df = pd.DataFrame({"x": [7, 7, 7], "y": [8, 8, 8]})
        path = _write_csv(df, str(tmp_path))
        result = analyze_duplicates(_make_request(path))
        assert result.findings[0].raw_data["total_rows"] == 3


# ΓöÇΓöÇ error handling ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class TestErrorHandling:
    def test_nonexistent_file_produces_finding_not_exception(self, tmp_path):
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            data_files=[os.path.join(str(tmp_path), "nonexistent.csv")],
        )
        result = analyze_duplicates(request)
        assert len(result.findings) == 1
        assert result.findings[0].category == "data_quality"
        assert result.success is True
