"""
tests/test_leakage.py — Unit tests for analyze_leakage()

LEAKAGE_CORR_THRESHOLD = 0.95  (|Pearson corr| >= this triggers a finding)
Target column: "TenYearCHD"

Synthetic datasets — 20 rows, fully deterministic (no random):
  df_clean:   two features with genuine but low correlation with target
  df_leaky:   df_clean + "leaked_feature" = TenYearCHD exactly (corr = 1.0)
  df_offset:  df_clean + "offset_feature" = TenYearCHD + 100 (corr = 1.0)
  df_no_target: no TenYearCHD column

Covers:
- Clean data produces no finding
- Perfect correlation (= 1.0) produces one finding per leaky column
- Finding category is "data_quality"
- Finding severity is CRITICAL
- leaky_column key in raw_data names the offending column
- correlation key in raw_data is close to 1.0
- target_column key in raw_data is "TenYearCHD"
- file_path is set
- Constant-offset column (corr = 1.0) also detected
- Non-leaky columns in the same file do not trigger findings
- Dataset without target column is skipped silently
- No data files → no findings
- Nonexistent file → finding, not exception
"""

import os

import pandas as pd
import pytest

from core.models import AnalysisRequest, ProjectInput, Severity
from analyzers.qa_analyzers import (
    analyze_leakage,
    LEAKAGE_CORR_THRESHOLD,
    TARGET_COLUMN,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_csv(df: pd.DataFrame, directory: str, name: str = "train.csv") -> str:
    path = os.path.join(directory, name)
    df.to_csv(path, index=False)
    return path


def _make_request(csv_path: str) -> AnalysisRequest:
    return AnalysisRequest(
        project_input=ProjectInput(path=os.path.dirname(csv_path), name="proj"),
        data_files=[csv_path],
    )


# ── deterministic base dataset ────────────────────────────────────────────────
# 20 rows; features have no systematic relationship with target.
_BASE = pd.DataFrame({
    "age":        [45, 52, 38, 61, 47, 55, 42, 58, 36, 49,
                   51, 44, 60, 37, 53, 48, 41, 56, 39, 50],
    "bmi":        [25, 29, 22, 31, 27, 26, 24, 30, 21, 28,
                   27, 25, 32, 22, 28, 26, 23, 29, 21, 27],
    TARGET_COLUMN: [0,  1,  0,  1,  0,  1,  0,  0,  0,  1,
                    0,  0,  1,  0,  1,  0,  0,  1,  0,  1],
})


def _df_clean():
    return _BASE.copy()


def _df_leaky():
    """Add a column that equals TenYearCHD exactly → corr = 1.0"""
    df = _BASE.copy()
    df["leaked_feature"] = df[TARGET_COLUMN]
    return df


def _df_offset():
    """Add a column = TenYearCHD + 100 → Pearson corr = 1.0"""
    df = _BASE.copy()
    df["offset_feature"] = df[TARGET_COLUMN] + 100
    return df


def _df_no_target():
    return _BASE.drop(columns=[TARGET_COLUMN])


# ── clean data ────────────────────────────────────────────────────────────────

class TestCleanData:
    def test_clean_no_finding(self, tmp_path):
        path = _write_csv(_df_clean(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings == []

    def test_success_true_on_clean(self, tmp_path):
        path = _write_csv(_df_clean(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.success is True

    def test_no_data_files_no_finding(self, tmp_path):
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            data_files=[],
        )
        result = analyze_leakage(request)
        assert result.findings == []


# ── perfect leakage (leaked_feature = target) ─────────────────────────────────

class TestPerfectLeakage:
    def test_leaky_column_produces_finding(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert len(result.findings) == 1

    def test_finding_category_data_quality(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings[0].category == "data_quality"

    def test_finding_severity_critical(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings[0].severity == Severity.CRITICAL

    def test_leaky_column_named_in_raw_data(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings[0].raw_data["leaky_column"] == "leaked_feature"

    def test_correlation_close_to_1_in_raw_data(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert abs(result.findings[0].raw_data["correlation"] - 1.0) < 0.001

    def test_target_column_in_raw_data(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings[0].raw_data["target_column"] == TARGET_COLUMN

    def test_file_path_set(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings[0].file_path == path

    def test_title_mentions_leakage(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert "leakage" in result.findings[0].title.lower() or \
               "correlated" in result.findings[0].title.lower()

    def test_success_true(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.success is True


# ── constant offset column (corr = 1.0) ──────────────────────────────────────

class TestOffsetColumn:
    def test_offset_column_also_detected(self, tmp_path):
        path = _write_csv(_df_offset(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert len(result.findings) == 1

    def test_offset_column_named_in_raw_data(self, tmp_path):
        path = _write_csv(_df_offset(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings[0].raw_data["leaky_column"] == "offset_feature"


# ── non-leaky columns are not flagged ─────────────────────────────────────────

class TestNonLeakyColumnsNotFlagged:
    def test_only_leaky_column_flagged_not_clean_ones(self, tmp_path):
        path = _write_csv(_df_leaky(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        flagged = {f.raw_data["leaky_column"] for f in result.findings}
        assert "age" not in flagged
        assert "bmi" not in flagged

    def test_two_leaky_columns_both_flagged(self, tmp_path):
        df = _df_leaky()
        df["another_leak"] = df[TARGET_COLUMN]   # second leaky column
        path = _write_csv(df, str(tmp_path))
        result = analyze_leakage(_make_request(path))
        flagged = {f.raw_data["leaky_column"] for f in result.findings}
        assert "leaked_feature" in flagged
        assert "another_leak"   in flagged


# ── no target column ──────────────────────────────────────────────────────────

class TestNoTargetColumn:
    def test_no_target_column_skipped_silently(self, tmp_path):
        path = _write_csv(_df_no_target(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.findings == []

    def test_no_target_success_true(self, tmp_path):
        path = _write_csv(_df_no_target(), str(tmp_path))
        result = analyze_leakage(_make_request(path))
        assert result.success is True


# ── error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_nonexistent_file_produces_finding_not_exception(self, tmp_path):
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            data_files=[os.path.join(str(tmp_path), "nonexistent.csv")],
        )
        result = analyze_leakage(request)
        assert len(result.findings) == 1
        assert result.success is True
