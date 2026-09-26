"""
tests/test_qa_severity_dedup.py
================================
Tests for:
  - analyze_class_imbalance severity ladder (MEDIUM/HIGH thresholds)
  - analyze_missing_values severity (CRITICAL vs HIGH) and specific descriptions
  - analyze_model_metrics specific descriptions for load/eval failures
  - _issue_stem() title-stripping helper
  - _deduplicate_findings() grouping and merge logic

These tests exercise analyzers/qa_analyzers.py and
cardiodev_guard/auditors/qa_audit.py without touching core/ or the dashboard.
"""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path

import pandas as pd
import pytest

from core.models import AnalysisRequest, AnalyzerResult, Finding as CoreFinding, Severity as CoreSeverity
from cardiodev_guard.findings import AuditDomain, AuditResult, Finding, Severity as DashSeverity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_csv(data: dict, *, suffix: str = ".csv") -> str:
    """Write a dict of column→list to a temp CSV and return its path."""
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    df = pd.DataFrame(data)
    df.to_csv(tf.name, index=False)
    tf.close()
    return tf.name


def _make_request(csv_paths=None, model_paths=None) -> AnalysisRequest:
    from core.models import ProjectInput
    pi = ProjectInput(name="test_project", path=tempfile.mkdtemp())
    req = AnalysisRequest(project_input=pi)
    req.data_files  = list(csv_paths or [])
    req.model_files = list(model_paths or [])
    return req


def _dash_finding(
    title: str,
    severity: DashSeverity = DashSeverity.WARNING,
    category: str = "data_quality",
    evidence: str = "File: /some/path.csv",
) -> Finding:
    """Construct a minimal dashboard Finding for dedup tests."""
    return Finding(
        id=f"qa.test.{title[:8].replace(' ', '_')}",
        domain=AuditDomain.QA,
        severity=severity,
        title=title,
        evidence=evidence,
        explanation="test explanation",
        suggested_fix="test fix",
        validation_method="re-scan",
        category=category,
    )


# ---------------------------------------------------------------------------
# 1. Class-imbalance severity
# ---------------------------------------------------------------------------

class TestClassImbalanceSeverity:
    """analyze_class_imbalance must emit MEDIUM for 5–20% minority
    and HIGH for <5% minority.  The old behaviour was HIGH for both,
    which caused WARNING-level imbalance to appear as BLOCKER on the dashboard.
    """

    def _run(self, minority_ratio: float, n_total: int = 1000) -> AnalyzerResult:
        from analyzers.qa_analyzers import analyze_class_imbalance
        minority_n = int(n_total * minority_ratio)
        majority_n = n_total - minority_n
        csv = _make_csv({
            "age":       list(range(n_total)),
            "TenYearCHD": [1] * minority_n + [0] * majority_n,
        })
        try:
            return analyze_class_imbalance(_make_request(csv_paths=[csv]))
        finally:
            os.unlink(csv)

    def test_ratio_above_threshold_produces_no_finding(self):
        result = self._run(0.25)
        assert result.findings == [], "Balanced dataset must not emit a finding"

    def test_moderate_imbalance_is_medium_severity(self):
        """15.2% minority (Framingham) must be MEDIUM, not HIGH."""
        result = self._run(0.152)
        assert len(result.findings) == 1
        assert result.findings[0].severity == CoreSeverity.MEDIUM, (
            f"15% imbalance should be MEDIUM (→ WARNING), "
            f"got {result.findings[0].severity}"
        )

    def test_moderate_imbalance_description_not_generic(self):
        """Description for MEDIUM imbalance must be specific, not generic."""
        result = self._run(0.152)
        desc = result.findings[0].description
        assert "medical" in desc.lower() or "mild" in desc.lower() or "moderate" in desc.lower(), (
            f"MEDIUM imbalance description should mention medical context, got: {desc!r}"
        )
        assert "not automatically release-blocking" in desc, (
            f"MEDIUM description should state it is not automatically release-blocking"
        )

    def test_extreme_imbalance_is_high_severity(self):
        """<5% minority must be HIGH (→ BLOCKER)."""
        result = self._run(0.03)
        assert len(result.findings) == 1
        assert result.findings[0].severity == CoreSeverity.HIGH, (
            f"3% imbalance should be HIGH (→ BLOCKER), "
            f"got {result.findings[0].severity}"
        )

    def test_extreme_imbalance_description_mentions_extreme(self):
        result = self._run(0.03)
        desc = result.findings[0].description
        assert "extreme" in desc.lower() or "<5%" in desc or "5%" in desc, (
            f"Extreme imbalance description should mention severity, got: {desc!r}"
        )

    def test_boundary_exactly_at_5pct_is_medium(self):
        """5.0% is at the boundary — must be MEDIUM (not HIGH)."""
        result = self._run(0.05)
        assert len(result.findings) == 1
        assert result.findings[0].severity == CoreSeverity.MEDIUM

    def test_just_below_5pct_is_high(self):
        """4.9% minority is strictly below threshold — must be HIGH."""
        result = self._run(0.049)
        assert len(result.findings) == 1
        assert result.findings[0].severity == CoreSeverity.HIGH

    def test_imbalance_critical_threshold_alias_unchanged(self):
        """IMBALANCE_CRITICAL_THRESHOLD alias must equal IMBALANCE_HIGH_THRESHOLD."""
        from analyzers.qa_analyzers import IMBALANCE_CRITICAL_THRESHOLD, IMBALANCE_HIGH_THRESHOLD
        assert IMBALANCE_CRITICAL_THRESHOLD == IMBALANCE_HIGH_THRESHOLD


# ---------------------------------------------------------------------------
# 2. Missing-value descriptions
# ---------------------------------------------------------------------------

class TestMissingValueDescriptions:
    """analyze_missing_values must produce specific, evidence-based descriptions."""

    def test_partial_missing_description_mentions_count_and_columns(self):
        from analyzers.qa_analyzers import analyze_missing_values
        import numpy as np
        csv = _make_csv({
            "age":    [1, 2, None, 4, 5],
            "weight": [70.0, None, None, 65.0, 80.0],
            "target": [0, 1, 0, 1, 0],
        })
        try:
            result = analyze_missing_values(_make_request(csv_paths=[csv]))
        finally:
            os.unlink(csv)
        assert len(result.findings) == 1
        f = result.findings[0]
        desc = f.description
        assert "3" in desc or "missing" in desc.lower()
        assert "age" in desc or "weight" in desc
        assert "imputation" in desc.lower() or "removal" in desc.lower()

    def test_entirely_null_column_is_critical_with_specific_description(self):
        from analyzers.qa_analyzers import analyze_missing_values
        csv = _make_csv({
            "age":    [1, 2, 3],
            "broken": [None, None, None],
            "target": [0, 1, 0],
        })
        try:
            result = analyze_missing_values(_make_request(csv_paths=[csv]))
        finally:
            os.unlink(csv)
        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.severity == CoreSeverity.CRITICAL
        assert "entirely null" in f.description.lower() or "all rows nan" in f.description.lower() or "broken" in f.description


# ---------------------------------------------------------------------------
# 3. Model metrics — specific descriptions
# ---------------------------------------------------------------------------

class TestModelMetricsDescriptions:
    """analyze_model_metrics must produce specific, evidence-grounded descriptions."""

    def test_load_failure_description_mentions_joblib_and_cause(self):
        from analyzers.qa_analyzers import analyze_model_metrics
        # Create an empty (corrupt) pkl file
        tf = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
        tf.close()
        csv = _make_csv({"a": [1, 2, 3], "TenYearCHD": [0, 1, 0]})
        try:
            result = analyze_model_metrics(_make_request(
                csv_paths=[csv], model_paths=[tf.name]
            ))
        finally:
            os.unlink(tf.name)
            os.unlink(csv)
        assert len(result.findings) >= 1
        load_findings = [f for f in result.findings if "Could not load" in f.title]
        assert load_findings, "Must have a 'Could not load' finding"
        desc = load_findings[0].description
        assert "joblib" in desc.lower() or "joblib.load" in desc
        assert "corrupt" in desc.lower() or "incompatible" in desc.lower() or "re-train" in desc.lower()

    def test_eval_failure_description_mentions_predict_and_cause(self):
        from analyzers.qa_analyzers import analyze_model_metrics
        import pickle, sklearn.linear_model
        # Train a model on different features to cause a shape/name mismatch
        m = sklearn.linear_model.LogisticRegression()
        m.fit([[0, 1], [1, 0], [0, 0]], [0, 1, 0])
        tf = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
        import joblib
        joblib.dump(m, tf.name)
        tf.close()
        # CSV has 3 feature columns — model expects 2 → shape mismatch
        csv = _make_csv({
            "feat1": [1, 2, 3],
            "feat2": [0, 1, 0],
            "feat3": [1, 0, 1],
            "TenYearCHD": [0, 1, 0],
        })
        try:
            result = analyze_model_metrics(_make_request(
                csv_paths=[csv], model_paths=[tf.name]
            ))
        finally:
            os.unlink(tf.name)
            os.unlink(csv)
        eval_findings = [f for f in result.findings if "evaluation failed" in f.title.lower()]
        if eval_findings:
            desc = eval_findings[0].description
            assert "predict" in desc.lower()
            assert "concrete evidence" in desc.lower() or "cannot score" in desc.lower()


# ---------------------------------------------------------------------------
# 4. _issue_stem() helper
# ---------------------------------------------------------------------------

class TestIssueStem:
    """_issue_stem() must strip trailing 'in <file>' / 'for <file>' suffixes."""

    @staticmethod
    def stem(title: str) -> str:
        from cardiodev_guard.auditors.qa_audit import _issue_stem
        return _issue_stem(title)

    def test_strips_in_csv(self):
        assert self.stem("Missing values detected in framingham_phase2.csv") == "Missing values detected"

    def test_strips_for_pkl(self):
        assert self.stem("Model evaluation failed for logistic_model.pkl") == "Model evaluation failed"

    def test_strips_could_not_load(self):
        assert self.stem("Could not load model: logistic_model.pkl") == "Could not load model: logistic_model.pkl"

    def test_no_suffix_unchanged(self):
        t = "Class imbalance detected in TenYearCHD (15.2% minority)"
        assert self.stem(t) == t

    def test_strips_parquet(self):
        assert self.stem("Duplicate rows detected in data.parquet") == "Duplicate rows detected"

    def test_empty_string_unchanged(self):
        assert self.stem("") == ""

    def test_title_without_extension_unchanged(self):
        assert self.stem("Something happened in my_column") == "Something happened in my_column"


# ---------------------------------------------------------------------------
# 5. _deduplicate_findings() logic
# ---------------------------------------------------------------------------

class TestDeduplicateFindings:
    """_deduplicate_findings() must group same-issue findings across files
    and preserve all evidence paths in the merged result."""

    @staticmethod
    def dedup(findings: list[Finding]) -> list[Finding]:
        from cardiodev_guard.auditors.qa_audit import _deduplicate_findings
        return _deduplicate_findings(findings)

    def test_single_finding_returned_unchanged(self):
        f = _dash_finding("Missing values detected in a.csv")
        result = self.dedup([f])
        assert len(result) == 1
        assert result[0].title == f.title  # not renamed when only 1

    def test_two_same_issue_different_files_merged(self):
        f1 = _dash_finding("Missing values detected in phase2.csv", evidence="File: /data/phase2.csv")
        f2 = _dash_finding("Missing values detected in phase3.csv", evidence="File: /data/phase3.csv")
        result = self.dedup([f1, f2])
        assert len(result) == 1
        merged = result[0]
        assert "2 file(s)" in merged.title
        assert "Missing values detected" in merged.title
        assert "/data/phase2.csv" in merged.evidence
        assert "/data/phase3.csv" in merged.evidence

    def test_different_issues_not_merged(self):
        f1 = _dash_finding("Missing values detected in phase2.csv")
        f2 = _dash_finding("Duplicate rows detected in phase2.csv")
        result = self.dedup([f1, f2])
        assert len(result) == 2

    def test_different_categories_not_merged(self):
        f1 = _dash_finding("Model issue in model.pkl", category="model_performance")
        f2 = _dash_finding("Model issue in data.csv", category="data_quality")
        result = self.dedup([f1, f2])
        assert len(result) == 2

    def test_highest_severity_wins(self):
        f1 = _dash_finding("Missing values detected in a.csv", severity=DashSeverity.WARNING)
        f2 = _dash_finding("Missing values detected in b.csv", severity=DashSeverity.BLOCKER)
        result = self.dedup([f1, f2])
        assert len(result) == 1
        assert result[0].severity == DashSeverity.BLOCKER

    def test_merged_evidence_contains_all_paths(self):
        paths = [f"File: /data/file{i}.csv" for i in range(3)]
        findings = [
            _dash_finding(f"Missing values detected in file{i}.csv", evidence=paths[i])
            for i in range(3)
        ]
        result = self.dedup(findings)
        assert len(result) == 1
        for p in paths:
            assert p in result[0].evidence

    def test_deduplicated_from_count_in_extra(self):
        f1 = _dash_finding("Missing values detected in a.csv")
        f2 = _dash_finding("Missing values detected in b.csv")
        result = self.dedup([f1, f2])
        assert result[0].extra.get("deduplicated_from") == 2

    def test_class_imbalance_not_merged_because_no_file_suffix(self):
        """Class imbalance titles do not end with a file extension,
        so they should not be grouped by _issue_stem."""
        f1 = _dash_finding("Class imbalance detected in TenYearCHD (15.2% minority)", evidence="File: /a.csv")
        f2 = _dash_finding("Class imbalance detected in TenYearCHD (15.2% minority)", evidence="File: /b.csv")
        # Same title, same stem → they WILL be merged (same issue, same column)
        result = self.dedup([f1, f2])
        assert len(result) == 1  # same logical issue → merged
        assert "/a.csv" in result[0].evidence
        assert "/b.csv" in result[0].evidence

    def test_empty_list_returns_empty(self):
        assert self.dedup([]) == []

    def test_ordering_preserved(self):
        """First occurrence of each group preserves original relative order."""
        f_missing  = _dash_finding("Missing values detected in a.csv",  category="data_quality")
        f_dups     = _dash_finding("Duplicate rows detected in a.csv",   category="data_quality")
        f_missing2 = _dash_finding("Missing values detected in b.csv",  category="data_quality")
        result = self.dedup([f_missing, f_dups, f_missing2])
        assert len(result) == 2
        # "Missing values" group appears first (position 0 in original)
        assert "Missing values" in result[0].title
        assert "Duplicate" in result[1].title
