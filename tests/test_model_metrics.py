"""
tests/test_model_metrics.py — Unit tests for analyze_model_metrics()

Model and dataset are built in-test using sklearn, then written to a
temporary directory so AnalysisRequest.model_files / data_files can be
populated with real paths.

Bad model:  DummyClassifier(strategy="most_frequent") on a balanced 20-sample
            binary dataset → ROC-AUC = 0.5 (below METRIC_MIN_ROC_AUC = 0.60)

Good model: LogisticRegression on a perfectly linearly separable 20-sample
            dataset → ROC-AUC ≈ 1.0 (above threshold → no finding)

Covers:
- Good model produces no finding
- Bad model produces one "model_performance" finding
- Finding severity is HIGH (roc_auc >= 0.50)
- roc_auc and accuracy are present in raw_data
- roc_auc value is close to expected
- model_file and eval_file keys in raw_data
- file_path on finding is set to model path
- No model files → no findings
- No data files → no findings
- Target column missing from CSV → no finding (skipped silently)
- Corrupt .pkl → finding with model_performance category, no exception
- success is True in all cases
"""

import os

import joblib
import pandas as pd
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression

from core.models import AnalysisRequest, ProjectInput, Severity
from analyzers.qa_analyzers import analyze_model_metrics, METRIC_MIN_ROC_AUC, TARGET_COLUMN


# ── dataset / model builders ─────────────────────────────────────────────────

def _make_bad_model_files(directory: str):
    """
    DummyClassifier(most_frequent) on a balanced 20-sample dataset.
    predict_proba returns constant probabilities → ROC-AUC = 0.5.
    """
    X = pd.DataFrame({
        "f1": [1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2],
        "f2": [1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2],
    })
    y = pd.Series([0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                   1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    model = DummyClassifier(strategy="most_frequent").fit(X, y)
    df = X.copy()
    df[TARGET_COLUMN] = y

    model_path = os.path.join(directory, "model.pkl")
    csv_path   = os.path.join(directory, "train.csv")
    joblib.dump(model, model_path)
    df.to_csv(csv_path, index=False)
    return model_path, csv_path


def _make_good_model_files(directory: str):
    """
    LogisticRegression on a perfectly separable 20-sample dataset.
    f1 > 0 → class 1; f1 < 0 → class 0. ROC-AUC ≈ 1.0.
    """
    f1_vals = [-3, -2, -1, -1, -2, -3, -2, -3, -1, -2,
                3,  2,  1,  1,  2,  3,  2,  3,  1,  2]
    X = pd.DataFrame({"f1": f1_vals, "f2": [0] * 20})
    y = pd.Series([0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                   1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    model = LogisticRegression(random_state=42, solver="lbfgs").fit(X, y)
    df = X.copy()
    df[TARGET_COLUMN] = y

    model_path = os.path.join(directory, "model.pkl")
    csv_path   = os.path.join(directory, "train.csv")
    joblib.dump(model, model_path)
    df.to_csv(csv_path, index=False)
    return model_path, csv_path


def _make_request(model_path: str, csv_path: str) -> AnalysisRequest:
    return AnalysisRequest(
        project_input=ProjectInput(path=os.path.dirname(model_path), name="proj"),
        model_files=[model_path],
        data_files=[csv_path],
    )


# ── good model (no finding) ───────────────────────────────────────────────────

class TestGoodModel:
    def test_good_model_no_finding(self, tmp_path):
        model_path, csv_path = _make_good_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert result.findings == []

    def test_success_true_on_good_model(self, tmp_path):
        model_path, csv_path = _make_good_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert result.success is True

    def test_analyzer_name_set(self, tmp_path):
        model_path, csv_path = _make_good_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert result.analyzer_name != ""


# ── bad model (finding expected) ──────────────────────────────────────────────

class TestBadModel:
    def test_bad_model_produces_finding(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert len(result.findings) == 1

    def test_finding_category_model_performance(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert result.findings[0].category == "model_performance"

    def test_severity_high_when_roc_auc_above_0_5(self, tmp_path):
        # DummyClassifier(most_frequent) ROC-AUC = 0.5 → HIGH (not CRITICAL)
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        # 0.5 >= 0.5 so HIGH (CRITICAL threshold is < 0.50)
        assert result.findings[0].severity == Severity.HIGH

    def test_roc_auc_in_raw_data(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert "roc_auc" in result.findings[0].raw_data

    def test_accuracy_in_raw_data(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert "accuracy" in result.findings[0].raw_data

    def test_roc_auc_value_below_threshold(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert result.findings[0].raw_data["roc_auc"] < METRIC_MIN_ROC_AUC

    def test_roc_auc_value_is_0_5_for_dummy(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert abs(result.findings[0].raw_data["roc_auc"] - 0.5) < 0.01

    def test_model_file_key_in_raw_data(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert "model_file" in result.findings[0].raw_data

    def test_eval_file_key_in_raw_data(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert "eval_file" in result.findings[0].raw_data

    def test_file_path_set_to_model_path(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert result.findings[0].file_path == model_path

    def test_success_true_on_bad_model(self, tmp_path):
        model_path, csv_path = _make_bad_model_files(str(tmp_path))
        result = analyze_model_metrics(_make_request(model_path, csv_path))
        assert result.success is True


# ── missing files / columns ───────────────────────────────────────────────────

class TestMissingFilesOrColumns:
    def test_no_model_files_no_finding(self, tmp_path):
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            model_files=[],
            data_files=[os.path.join(str(tmp_path), "train.csv")],
        )
        result = analyze_model_metrics(request)
        assert result.findings == []

    def test_no_data_files_no_finding(self, tmp_path):
        model_path = os.path.join(str(tmp_path), "model.pkl")
        joblib.dump(DummyClassifier().fit([[0], [1]], [0, 1]), model_path)
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            model_files=[model_path],
            data_files=[],
        )
        result = analyze_model_metrics(request)
        assert result.findings == []

    def test_target_column_absent_no_finding(self, tmp_path):
        model_path, _ = _make_bad_model_files(str(tmp_path))
        # Write a CSV without the target column
        csv_no_target = os.path.join(str(tmp_path), "no_target.csv")
        pd.DataFrame({"f1": [1, 2], "f2": [3, 4]}).to_csv(csv_no_target, index=False)
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            model_files=[model_path],
            data_files=[csv_no_target],
        )
        result = analyze_model_metrics(request)
        assert result.findings == []

    def test_corrupt_pkl_produces_finding_not_exception(self, tmp_path):
        bad_model = os.path.join(str(tmp_path), "bad_model.pkl")
        with open(bad_model, "wb") as f:
            f.write(b"this is not a valid pickle file")
        csv_path = os.path.join(str(tmp_path), "train.csv")
        pd.DataFrame({"f1": [1, 2], TARGET_COLUMN: [0, 1]}).to_csv(csv_path, index=False)
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            model_files=[bad_model],
            data_files=[csv_path],
        )
        result = analyze_model_metrics(request)
        assert len(result.findings) == 1
        assert result.findings[0].category == "model_performance"
        assert result.success is True

    def test_nonexistent_model_file_produces_finding_not_exception(self, tmp_path):
        csv_path = os.path.join(str(tmp_path), "train.csv")
        pd.DataFrame({"f1": [1, 2], TARGET_COLUMN: [0, 1]}).to_csv(csv_path, index=False)
        request = AnalysisRequest(
            project_input=ProjectInput(path=str(tmp_path), name="proj"),
            model_files=[os.path.join(str(tmp_path), "missing.pkl")],
            data_files=[csv_path],
        )
        result = analyze_model_metrics(request)
        assert len(result.findings) == 1
        assert result.success is True
