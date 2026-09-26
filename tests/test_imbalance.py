"""
tests/test_imbalance.py ΓÇö Unit tests for analyze_class_imbalance()

Target column convention: "TenYearCHD" (matches actual project data)
Threshold constants from analyzers.qa_analyzers:
  IMBALANCE_THRESHOLD          = 0.20  ΓåÆ minority fraction < 0.20 triggers finding
  IMBALANCE_CRITICAL_THRESHOLD = 0.05  ΓåÆ minority fraction < 0.05 triggers CRITICAL

Covers:
- Balanced dataset (50/50) produces no finding
- Mild imbalance (85/15) triggers finding (minority_ratio 0.15 < 0.20)
- Severe imbalance (95/5) triggers CRITICAL finding
- Finding category is "data_quality"
- minority_ratio in raw_data is correct
- minority_class / majority_class in raw_data correct
- minority_count / majority_count in raw_data correct
- target_column in raw_data is set
- file_path is set
- Dataset without target column is skipped silently (no finding, no crash)
- No data files ΓåÆ no findings
- Nonexistent file produces finding, not exception
"""

import os

import pandas as pd
import pytest

from core.models import AnalysisRequest, ProjectInput, Severity
from analyzers.qa_analyzers import (
    analyze_class_imbalance,
    IMBALANCE_THRESHOLD,
    IMBALANCE_CRITICAL_THRESHOLD,
    TARGET_COLUMN,
)


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


# Deterministic datasets ΓÇö no random, explicit values
DF_BALANCED   = pd.DataFrame({"TenYearCHD": [0] * 50 + [1] * 50})          # 50/50
DF_MILD       = pd.DataFrame({"TenYearCHD": [0] * 85 + [1] * 15})          # 85/15  ΓåÆ HIGH
DF_SEVERE     = pd.DataFrame({"TenYearCHD": [0] * 95 + [1] * 5})           # 95/5   ΓåÆ CRITICAL
DF_NO_TARGET  = pd.DataFrame({"age": [40, 50, 60], "bmi": [25, 30, 28]})   # no target column


# ΓöÇΓöÇ balanced (no finding) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class TestBalanced:
    def test_balanced_no_finding(self, tmp_path):
        path = _write_csv(DF_BALANCED, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings == []

    def test_success_true_on_balanced(self, tmp_path):
        path = _write_csv(DF_BALANCED, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.success is True

    def test_no_data_files_no_finding(self, tmp_path):
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            data_files=[],
        )
        result = analyze_class_imbalance(request)
        assert result.findings == []


# ΓöÇΓöÇ mild imbalance (85/15) ΓåÆ HIGH ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class TestMildImbalance:
    def test_mild_imbalance_produces_finding(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert len(result.findings) == 1

    def test_finding_category_data_quality(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].category == "data_quality"

    def test_severity_is_high_for_mild(self, tmp_path):
        # 15% minority < IMBALANCE_THRESHOLD (0.20) but >= IMBALANCE_CRITICAL_THRESHOLD (0.05)
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].severity == Severity.HIGH

    def test_minority_ratio_correct(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        ratio = result.findings[0].raw_data["minority_ratio"]
        assert abs(ratio - 0.15) < 0.001

    def test_minority_class_is_1(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].raw_data["minority_class"] == 1

    def test_majority_class_is_0(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].raw_data["majority_class"] == 0

    def test_minority_count_correct(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].raw_data["minority_count"] == 15

    def test_majority_count_correct(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].raw_data["majority_count"] == 85

    def test_target_column_in_raw_data(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].raw_data["target_column"] == TARGET_COLUMN

    def test_file_path_set(self, tmp_path):
        path = _write_csv(DF_MILD, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].file_path == path


# ΓöÇΓöÇ severe imbalance (95/5) ΓåÆ CRITICAL ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class TestSevereImbalance:
    def test_severe_imbalance_produces_finding(self, tmp_path):
        path = _write_csv(DF_SEVERE, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert len(result.findings) == 1

    def test_severity_is_critical_for_severe(self, tmp_path):
        # 5% minority < IMBALANCE_CRITICAL_THRESHOLD (0.05) is NOT strictly less, it equals
        # so test at 4% to be unambiguous; but 5/100 = 0.05 which is NOT < 0.05
        # Test with df that has 4% minority instead
        df = pd.DataFrame({"TenYearCHD": [0] * 96 + [1] * 4})
        path = _write_csv(df, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].severity == Severity.CRITICAL

    def test_severe_minority_ratio_correct(self, tmp_path):
        path = _write_csv(DF_SEVERE, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        ratio = result.findings[0].raw_data["minority_ratio"]
        assert abs(ratio - 0.05) < 0.001

    def test_severe_minority_count_correct(self, tmp_path):
        path = _write_csv(DF_SEVERE, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings[0].raw_data["minority_count"] == 5


# ΓöÇΓöÇ no target column ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class TestNoTargetColumn:
    def test_no_target_column_skipped_silently(self, tmp_path):
        path = _write_csv(DF_NO_TARGET, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.findings == []

    def test_no_target_column_success_true(self, tmp_path):
        path = _write_csv(DF_NO_TARGET, str(tmp_path))
        result = analyze_class_imbalance(_make_request(path))
        assert result.success is True


# ΓöÇΓöÇ error handling ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

class TestErrorHandling:
    def test_nonexistent_file_produces_finding_not_exception(self, tmp_path):
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            data_files=[os.path.join(str(tmp_path), "nonexistent.csv")],
        )
        result = analyze_class_imbalance(request)
        assert len(result.findings) == 1
        assert result.success is True
