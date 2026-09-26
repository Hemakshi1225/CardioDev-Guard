# Part B: Before vs After Measurement

**Scope:** CardioDev Guard project — automated scanner covering three audit
domains: ML, QA, and RELEASE. QA-domain analyzers implemented in
`analyzers/qa_analyzers.py`; integration adapter in
`cardiodev_guard/auditors/qa_audit.py`.

---

## 1. Manual Workflow (Before CardioDev Guard)

A data scientist reviewing the Framingham Heart Study dataset and a trained
`.pkl` model for release would typically follow these steps manually:

1. **Open the CSV** in a spreadsheet tool or Jupyter notebook.
2. **Scan for missing values** — call `df.isnull().sum()` per column, inspect
   results, decide severity by eye.
3. **Check for duplicate rows** — call `df.duplicated().sum()`, manually
   compute the duplicate fraction, decide severity by eye.
4. **Inspect class distribution** — call `df['TenYearCHD'].value_counts()`,
   compute the minority ratio manually, compare to an ad-hoc threshold.
5. **Assess feature correlations** — compute a correlation matrix, visually
   scan for columns that are nearly identical to the target, pick a threshold
   by judgement.
6. **Evaluate the model** — load the `.pkl` with `joblib`, call
   `predict_proba`, compute ROC-AUC and accuracy, compare to an informal
   acceptability bar.
7. **Record findings** — write notes in a document or ticket, categorise by
   severity manually.
8. **Repeat** for every new version of the dataset or model.

Each step is performed ad hoc, with no consistent thresholds, no machine-
readable output, and no integration into a release gate.

---

## 2. CardioDev Guard Automated Workflow (After)

```
project_path (str)
    └─> core.project_loader.load_project()          # discovers all .csv, .pkl files
            └─> AnalysisRequest
                    ├─> analyze_missing_values()     # NaN scan — all CSV files
                    ├─> analyze_duplicates()         # exact-duplicate row scan
                    ├─> analyze_class_imbalance()    # minority-fraction check on TenYearCHD
                    ├─> analyze_leakage()            # Pearson |corr| >= 0.95 with target
                    └─> analyze_model_metrics()      # ROC-AUC / accuracy per .pkl
                            └─> core.aggregator.aggregate()
                                    └─> core.explainer.explain()
                                            └─> core.recommender.recommend()
                                                    └─> StructuredOutput
                                                            └─> cardiodev_guard/auditors/qa_audit.py
                                                                    └─> ScanReport  →  dashboard
```

The pipeline is invoked with:

```python
from core.orchestrator import run_pipeline
from analyzers.qa_analyzers import (
    analyze_missing_values, analyze_duplicates,
    analyze_class_imbalance, analyze_model_metrics, analyze_leakage,
)
output = run_pipeline(project_path, [
    analyze_missing_values, analyze_duplicates,
    analyze_class_imbalance, analyze_model_metrics, analyze_leakage,
])
```

Results are injected into the dashboard via `qa_audit.inject_results()` and
consumed by `cardiodev_guard/scanner.py`'s `run_scan()`, which produces a
`ScanReport` with a machine-readable `release_ready` boolean and a
`release_status_label` string.

The scanner covers three audit domains: **ML**, **QA**, and **RELEASE**.

---

## 3. Review Time — Manual vs Automated

| Phase | Manual workflow | CardioDev Guard automated |
|---|---|---|
| Data + model discovery | Manually locate files in the project tree | `load_project()` walks the directory tree automatically |
| Missing-value check | Open notebook, write `isnull()` code, inspect output | `analyze_missing_values()` runs programmatically on every `.csv` |
| Duplicate-row check | Write `duplicated()` code, compute fraction, apply judgement | `analyze_duplicates()` applies a fixed threshold (≥ 50% → CRITICAL) |
| Class-imbalance check | Write `value_counts()` code, compute ratio, compare to informal bar | `analyze_class_imbalance()` applies thresholds 0.20 (HIGH) / 0.05 (CRITICAL) |
| Leakage scan | Build correlation matrix, visually scan every column | `analyze_leakage()` applies threshold \|corr\| ≥ 0.95 across all features |
| Model evaluation | Load model, run `predict_proba`, compute metrics, compare to informal bar | `analyze_model_metrics()` applies minimum ROC-AUC 0.60; CRITICAL if < 0.50 |
| Output packaging | Write notes to doc/ticket | `StructuredOutput` with severity-sorted findings and priority-ranked recommendations |
| Release gate | Human judgement call | `ScanReport.release_ready` boolean; `release_status_label` string |
| **Automated scan time (this project)** | **Not measured — see limitation below** | **0.226 seconds** |

> **Limitation — manual audit time not measured:** The wall-clock time for a
> manual review pass has not been recorded in this project. No time-saving
> percentage or ratio is claimed. The 0.226-second figure is the actual
> automated scan elapsed time observed for this project; it is not compared
> to a manual baseline.

The automated test suite (`pytest tests/`) ran **125 tests** and all 125
passed. Test run time is separate from the scanner scan time and is not
reported here as a scan-performance measurement.

---

## 4. Manual Checks vs Automated Checks

| Check | Manual (before) | Automated (after) | Threshold enforced |
|---|---|---|---|
| Missing values — partial | Visual inspection of `isnull().sum()` | `analyze_missing_values()` raises `Severity.HIGH` | Any column with ≥ 1 NaN |
| Missing values — fully null column | Visual inspection | `analyze_missing_values()` raises `Severity.CRITICAL` | Column where `df[col].isnull().all()` is True |
| Duplicate rows — moderate | Visual / `duplicated()` + manual fraction | `analyze_duplicates()` raises `Severity.HIGH` | Duplicate fraction < 50 % |
| Duplicate rows — severe | Visual judgement | `analyze_duplicates()` raises `Severity.CRITICAL` | Duplicate fraction ≥ 50 % |
| Class imbalance — mild | `value_counts()` + informal threshold | `analyze_class_imbalance()` raises `Severity.HIGH` | Minority fraction < 20 % |
| Class imbalance — severe | `value_counts()` + informal threshold | `analyze_class_imbalance()` raises `Severity.CRITICAL` | Minority fraction < 5 % |
| Data leakage | Manual scan of correlation matrix | `analyze_leakage()` raises `Severity.CRITICAL` | \|Pearson corr\| ≥ 0.95 |
| Model ROC-AUC — below minimum | Load model + manual metric computation | `analyze_model_metrics()` raises `Severity.HIGH` | ROC-AUC < 0.60 |
| Model ROC-AUC — below chance | Load model + manual metric computation | `analyze_model_metrics()` raises `Severity.CRITICAL` | ROC-AUC < 0.50 |
| Unreadable / missing file | Noticed incidentally | All five analyzers surface a `Severity.HIGH` finding instead of raising | File read exception caught |
| QA-domain release gate | Human go/no-go decision | `ScanReport.release_ready` (False if any BLOCKER) | Any BLOCKER finding in QA domain |

**Total distinct automated checks: 11** (compared to an informal, ad-hoc
manual equivalent that applies no consistent thresholds).

---

## 5. Actual Scan Results — Observed Evidence

### This project (CardioDev-Guard)

A `run_scan()` call on this project completed in **0.226 seconds**
(0.2259701 s). The scan covered three audit domains: **ML**, **QA**, and
**RELEASE**.

| Metric | Value |
|---|---|
| Scan elapsed time | 0.226 s (0.2259701 s) |
| Audit domains covered | 3 (ML, QA, RELEASE) |
| Findings | 0 |
| Blockers | 0 |
| Warnings | 0 |
| Passes | 0 |
| `release_ready` | True |

### Second sample project — Phase 3: Framingham App

The scanner was also run against the Phase 3 Framingham App project.

**Initial scan result:**

| Metric | Value |
|---|---|
| Findings | 0 |
| Blockers | 0 |
| Warnings | 0 |
| Passes | 0 |
| Release readiness | READY FOR RELEASE |

**Re-check result (2026-09-26 14:04:38):**

| Metric | Value |
|---|---|
| Findings | 0 |
| Blockers | 0 |
| Warnings | 0 |
| Passes | 0 |
| Re-check timestamp | 2026-09-26 14:04:38 |

Both runs confirmed release readiness for the Phase 3 project with no
blockers or warnings detected.

---

## 6. What the Automated Pipeline Guarantees Regardless of Data

Based on the verified test suite (125/125 passing):

| Guarantee | Evidence |
|---|---|
| A partially-null column always produces a `HIGH` finding | `TestOneNaN::test_severity_is_high_for_partial_nan` |
| A fully-null column always produces a `CRITICAL` finding | `TestAllNullColumn::test_entirely_null_column_is_critical` |
| Moderate duplicate fraction (< 50 %) always produces a `HIGH` finding | `TestOneDuplicate::test_severity_is_high` |
| Duplicate fraction ≥ 50 % always produces a `CRITICAL` finding | `TestAllDuplicates::test_all_dups_severity_critical` |
| Minority fraction between 5 % and 20 % always produces a `HIGH` finding | `TestMildImbalance::test_severity_is_high_for_mild` |
| Minority fraction < 5 % always produces a `CRITICAL` finding | `TestSevereImbalance::test_severity_is_critical_for_severe` |
| Perfect feature–target correlation always produces a `CRITICAL` leakage finding | `TestPerfectLeakage::test_finding_severity_critical` |
| Model ROC-AUC below 0.60 always produces a `HIGH` finding | `TestBadModel::test_roc_auc_value_below_threshold` |
| A QA BLOCKER finding always sets `ScanReport.release_ready = False` | `TestScannerQualityIndicators::test_qa_blocker_makes_report_not_release_ready` |
| A file-read error never crashes the pipeline — a finding is raised instead | `TestErrorHandling` classes across all five test modules |

---

## 7. Known Limitations

| Limitation | Detail |
|---|---|
| Manual audit time not measured | No wall-clock time for a manual review pass was recorded. No time-saving percentage or ratio is claimed. |
| QA scan result shows 0 passes | Both scan runs returned 0 findings, 0 blockers, 0 warnings, and 0 passes. The 0-passes value is the observed output; it may reflect that no individual passing checks are surfaced when there are no findings. |
| `TARGET_COLUMN` hard-coded | `analyze_class_imbalance()` and `analyze_leakage()` use the constant `"TenYearCHD"`. Datasets with a different target column name are silently skipped. |
| Leakage detection is Pearson-only | Non-linear relationships between features and the target will not be detected. |
