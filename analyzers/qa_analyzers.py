"""
analyzers/qa_analyzers.py ΓÇö Vanshika's QA-domain analyzer functions
====================================================================

Five analyzer callables that conform to the core pipeline contract:

    def <name>(request: AnalysisRequest) -> AnalyzerResult

Each function reads the project's data files (and, for model metrics,
the model files) from the supplied AnalysisRequest, runs a specific
data-quality or model-quality check, and returns an AnalyzerResult
containing zero or more Finding objects.

Functions
---------
analyze_missing_values   ΓÇö detect NaN values in CSV files
analyze_duplicates       ΓÇö detect duplicate rows in CSV files
analyze_class_imbalance  ΓÇö detect class imbalance in binary target column
analyze_model_metrics    ΓÇö evaluate loaded model ROC-AUC / accuracy
analyze_leakage          ΓÇö detect feature-target correlation leakage

All five functions are designed to be registered with the core pipeline:

    from core.orchestrator import run_pipeline
    from analyzers.qa_analyzers import (
        analyze_missing_values, analyze_duplicates,
        analyze_class_imbalance, analyze_model_metrics, analyze_leakage,
    )
    output = run_pipeline(project_path, [
        analyze_missing_values, analyze_duplicates,
        analyze_class_imbalance, analyze_model_metrics, analyze_leakage,
    ])

They can also inject results into the dashboard via qa_audit:

    from cardiodev_guard.auditors import qa_audit
    from cardiodev_guard.findings import AuditResult, AuditDomain
    # (build AuditResult from these analyzer outputs, then inject)
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd
import joblib

from core.models import AnalysisRequest, AnalyzerResult, Finding, Severity

# ΓöÇΓöÇ tuneable thresholds ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
# Exposed as module-level constants so tests can inspect/override them.
MISSING_CRITICAL_THRESHOLD = 1.0   # fraction: entire column missing ΓåÆ CRITICAL
IMBALANCE_THRESHOLD        = 0.20  # minority fraction below this ΓåÆ finding
IMBALANCE_CRITICAL_THRESHOLD = 0.05  # minority fraction below this ΓåÆ CRITICAL
METRIC_MIN_ROC_AUC         = 0.60  # ROC-AUC below this ΓåÆ finding
LEAKAGE_CORR_THRESHOLD     = 0.95  # |Pearson corr| >= this ΓåÆ leakage finding
TARGET_COLUMN              = "TenYearCHD"  # default target column name


# ΓöÇΓöÇ 1. Missing value detection ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def analyze_missing_values(request: AnalysisRequest) -> AnalyzerResult:
    """Detect columns that contain NaN values in every data file."""
    result = AnalyzerResult(analyzer_name="Missing Value Analyzer")

    for csv_path in request.data_files:
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            result.findings.append(Finding(
                severity=Severity.HIGH,
                category="data_quality",
                title=f"Could not read data file: {os.path.basename(csv_path)}",
                description=str(exc),
                file_path=csv_path,
            ))
            continue

        missing_per_col = df.isnull().sum()
        affected = {col: int(cnt) for col, cnt in missing_per_col.items() if cnt > 0}
        if not affected:
            continue

        total_missing = sum(affected.values())
        total_cells   = len(df) * len(df.columns)
        # CRITICAL when any column is entirely NaN
        entirely_null = [c for c in affected if df[c].isnull().all()]
        severity = Severity.CRITICAL if entirely_null else Severity.HIGH

        result.findings.append(Finding(
            severity=severity,
            category="data_quality",
            title=f"Missing values detected in {os.path.basename(csv_path)}",
            description=(
                f"{total_missing} missing value(s) found across "
                f"{len(affected)} column(s): {list(affected.keys())}"
            ),
            file_path=csv_path,
            raw_data={
                "missing_count":      total_missing,
                "affected_columns":   list(affected.keys()),
                "per_column":         affected,
                "entirely_null_cols": entirely_null,
            },
        ))

    return result


# ΓöÇΓöÇ 2. Duplicate row detection ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def analyze_duplicates(request: AnalysisRequest) -> AnalyzerResult:
    """Detect exact duplicate rows in every data file."""
    result = AnalyzerResult(analyzer_name="Duplicate Row Analyzer")

    for csv_path in request.data_files:
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            result.findings.append(Finding(
                severity=Severity.HIGH,
                category="data_quality",
                title=f"Could not read data file: {os.path.basename(csv_path)}",
                description=str(exc),
                file_path=csv_path,
            ))
            continue

        n_dups = int(df.duplicated().sum())
        if n_dups == 0:
            continue

        total_rows         = len(df)
        duplicate_fraction = round(n_dups / total_rows, 4)
        severity = Severity.CRITICAL if duplicate_fraction >= 0.5 else Severity.HIGH

        result.findings.append(Finding(
            severity=severity,
            category="data_quality",
            title=f"Duplicate rows detected in {os.path.basename(csv_path)}",
            description=(
                f"{n_dups} duplicate row(s) found out of {total_rows} "
                f"({duplicate_fraction:.1%} of the dataset)."
            ),
            file_path=csv_path,
            raw_data={
                "duplicate_count":    n_dups,
                "total_rows":         total_rows,
                "duplicate_fraction": duplicate_fraction,
            },
        ))

    return result


# ΓöÇΓöÇ 3. Class imbalance detection ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def analyze_class_imbalance(
    request: AnalysisRequest,
    target_column: str = TARGET_COLUMN,
) -> AnalyzerResult:
    """Detect class imbalance in a binary target column."""
    result = AnalyzerResult(analyzer_name="Class Imbalance Analyzer")

    for csv_path in request.data_files:
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            result.findings.append(Finding(
                severity=Severity.HIGH,
                category="data_quality",
                title=f"Could not read data file: {os.path.basename(csv_path)}",
                description=str(exc),
                file_path=csv_path,
            ))
            continue

        if target_column not in df.columns:
            continue  # not a labelled dataset ΓÇö skip silently

        counts        = df[target_column].value_counts()
        minority_cls  = counts.idxmin()
        majority_cls  = counts.idxmax()
        minority_cnt  = int(counts[minority_cls])
        majority_cnt  = int(counts[majority_cls])
        total         = minority_cnt + majority_cnt
        minority_ratio = minority_cnt / total if total > 0 else 0.0

        if minority_ratio >= IMBALANCE_THRESHOLD:
            continue  # balanced enough

        severity = (
            Severity.CRITICAL if minority_ratio < IMBALANCE_CRITICAL_THRESHOLD
            else Severity.HIGH
        )

        result.findings.append(Finding(
            severity=severity,
            category="data_quality",
            title=(
                f"Class imbalance detected in {target_column} "
                f"({minority_ratio:.1%} minority)"
            ),
            description=(
                f"Minority class '{minority_cls}' has only {minority_cnt} samples "
                f"({minority_ratio:.1%}) vs majority class '{majority_cls}' "
                f"with {majority_cnt} samples."
            ),
            file_path=csv_path,
            raw_data={
                "minority_class":  minority_cls,
                "minority_count":  minority_cnt,
                "minority_ratio":  round(minority_ratio, 4),
                "majority_class":  majority_cls,
                "majority_count":  majority_cnt,
                "target_column":   target_column,
            },
        ))

    return result


# ΓöÇΓöÇ 4. Model metric detection ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def analyze_model_metrics(
    request: AnalysisRequest,
    target_column: str = TARGET_COLUMN,
) -> AnalyzerResult:
    """Load each .pkl model and evaluate ROC-AUC / accuracy on data files."""
    from sklearn.metrics import roc_auc_score, accuracy_score

    result = AnalyzerResult(analyzer_name="Model Metrics Analyzer")

    if not request.model_files:
        return result
    if not request.data_files:
        return result

    for model_path in request.model_files:
        try:
            model = joblib.load(model_path)
        except Exception as exc:
            result.findings.append(Finding(
                severity=Severity.HIGH,
                category="model_performance",
                title=f"Could not load model: {os.path.basename(model_path)}",
                description=str(exc),
                file_path=model_path,
            ))
            continue

        for csv_path in request.data_files:
            try:
                df = pd.read_csv(csv_path)
            except Exception as exc:
                result.findings.append(Finding(
                    severity=Severity.HIGH,
                    category="model_performance",
                    title=f"Could not read eval file: {os.path.basename(csv_path)}",
                    description=str(exc),
                    file_path=csv_path,
                ))
                continue

            if target_column not in df.columns:
                continue

            X = df.drop(columns=[target_column])
            y = df[target_column]

            try:
                y_pred  = model.predict(X)
                y_proba = model.predict_proba(X)[:, 1]
                auc     = round(float(roc_auc_score(y, y_proba)), 4)
                acc     = round(float(accuracy_score(y, y_pred)), 4)
            except Exception as exc:
                result.findings.append(Finding(
                    severity=Severity.HIGH,
                    category="model_performance",
                    title=f"Model evaluation failed for {os.path.basename(model_path)}",
                    description=str(exc),
                    file_path=model_path,
                ))
                continue

            if auc >= METRIC_MIN_ROC_AUC:
                continue  # metrics are acceptable

            severity = Severity.CRITICAL if auc < 0.50 else Severity.HIGH

            result.findings.append(Finding(
                severity=severity,
                category="model_performance",
                title=f"Low ROC-AUC score: {auc:.2f} ({os.path.basename(model_path)})",
                description=(
                    f"Model '{os.path.basename(model_path)}' achieved ROC-AUC={auc} "
                    f"and accuracy={acc} on '{os.path.basename(csv_path)}'. "
                    f"Minimum acceptable ROC-AUC is {METRIC_MIN_ROC_AUC}."
                ),
                file_path=model_path,
                raw_data={
                    "roc_auc":    auc,
                    "accuracy":   acc,
                    "model_file": model_path,
                    "eval_file":  csv_path,
                },
            ))

    return result


# ΓöÇΓöÇ 5. Data leakage detection ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

def analyze_leakage(
    request: AnalysisRequest,
    target_column: str = TARGET_COLUMN,
) -> AnalyzerResult:
    """Detect features with near-perfect Pearson correlation with the target."""
    result = AnalyzerResult(analyzer_name="Leakage Detector")

    for csv_path in request.data_files:
        try:
            df = pd.read_csv(csv_path)
        except Exception as exc:
            result.findings.append(Finding(
                severity=Severity.HIGH,
                category="data_quality",
                title=f"Could not read data file: {os.path.basename(csv_path)}",
                description=str(exc),
                file_path=csv_path,
            ))
            continue

        if target_column not in df.columns:
            continue

        target = df[target_column]
        feature_cols = [c for c in df.columns if c != target_column]

        for col in feature_cols:
            try:
                corr = df[col].corr(target)
            except Exception:
                continue

            if pd.isna(corr):
                continue

            if abs(corr) < LEAKAGE_CORR_THRESHOLD:
                continue

            result.findings.append(Finding(
                severity=Severity.CRITICAL,
                category="data_quality",
                title=(
                    f"Potential data leakage: {col} highly correlated "
                    f"with {target_column} (corr={corr:.4f})"
                ),
                description=(
                    f"Feature '{col}' has a Pearson correlation of {corr:.4f} "
                    f"with target '{target_column}'. Values at or above "
                    f"{LEAKAGE_CORR_THRESHOLD} indicate possible data leakage."
                ),
                file_path=csv_path,
                raw_data={
                    "leaky_column":   col,
                    "correlation":    round(float(corr), 4),
                    "target_column":  target_column,
                },
            ))

    return result
