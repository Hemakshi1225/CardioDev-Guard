# Part B: Before vs After Measurement

**Scope:** Vanshika's QA-domain work — five analyzer functions in
`analyzers/qa_analyzers.py`, six test modules in `tests/`, and the
`cardiodev_guard/auditors/qa_audit.py` integration adapter.

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
| **Total wall-clock time** | **⚠ PLACEHOLDER — must be measured** | **⚠ PLACEHOLDER — must be measured** |

> **How to measure:** Record the wall-clock time a reviewer spends on a
> single manual review pass of `framingham.csv` and its associated model.
> Record the elapsed time of a single `run_pipeline()` call on the same
> project directory. Both measurements must be taken on the same machine
> with the same dataset and model.

The automated test suite (`pytest tests/`) ran **125 tests in 3.03 seconds**
on Python 3.14.5 on a Windows 10 x64 machine. This is the only concrete
timing measurement available from the current codebase.

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

## 5. Manually Identified Issues vs Automatically Identified Issues

### Issues identifiable on `framingham.csv` without CardioDev Guard

The raw Framingham dataset (`framingham.csv`, also present as
`phase 2/framingham.csv`) is a 4,238-row, 16-column CSV with a binary target
column `TenYearCHD`.

| Potential issue | Detectable manually? | Notes |
|---|---|---|
| Missing values | Yes — requires loading file and inspecting each column | Tedious for 16 columns; easy to miss low-frequency NaNs |
| Duplicate rows | Yes — requires `duplicated()` call | Fraction threshold is subjective |
| Class imbalance | Yes — known issue in the Framingham dataset | Threshold below which a project is blocked is not standardised |
| Data leakage | Partially — only obvious if reviewer checks the correlation matrix | Subtle engineered features can be missed |
| Low model ROC-AUC | Yes — if reviewer knows to run the evaluation | Minimum acceptable threshold is not standardised |

> **Note on actual findings:** The automated analyzers have not been run
> against `framingham.csv` with a trained `.pkl` model in this session,
> because no `.pkl` model file is present in the project root or `phase 2/`
> directory. To obtain the actual finding output, run:
>
> ```python
> from core.orchestrator import run_pipeline
> from analyzers.qa_analyzers import (
>     analyze_missing_values, analyze_duplicates,
>     analyze_class_imbalance, analyze_model_metrics, analyze_leakage,
> )
> output = run_pipeline(".", [
>     analyze_missing_values, analyze_duplicates,
>     analyze_class_imbalance, analyze_model_metrics, analyze_leakage,
> ])
> for f in output.findings:
>     print(f.severity.name, f.title)
> print(output.summary)
> ```
>
> The `overall_status` and the full finding list constitute the "after"
> measurement for this section. **⚠ PLACEHOLDER — run the above and record
> the output here.**

### What the automated pipeline guarantees regardless of data

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

## Placeholders Requiring Real Measurement

The following items cannot be determined from the codebase alone and must be
recorded from an actual run:

| Placeholder | What must be measured |
|---|---|
| Manual review wall-clock time | Time a reviewer spends doing all five checks by hand on `framingham.csv` and a trained model |
| Automated pipeline wall-clock time | Elapsed time of `run_pipeline()` on the project directory (excluding test setup) |
| Actual findings on `framingham.csv` | Run the pipeline with a `.pkl` model present; record `output.findings` and `output.summary` |
| Number of issues found manually vs automatically | Compare the list produced manually by a reviewer to the list produced by the pipeline on the same dataset + model |
