# Final Quality Report — CardioDev-Guard (Vanshika QA Domain)

**Branch:** Vanshika  
**Scope:** QA-domain work — `analyzers/qa_analyzers.py`, six test modules in `tests/`, and `cardiodev_guard/auditors/qa_audit.py`  
**Date prepared:** 2025-07  
**Prepared from:** existing codebase, test suite, and `docs/impact.md`

---

## 1. Project Overview

CardioDev-Guard is an AI-powered ML project quality assistant that analyses
datasets and models to detect issues, suggest fixes, and assess release
readiness. The Vanshika QA domain contributes five analyzer functions and the
integration adapter that connects them to the shared dashboard pipeline.

**QA-domain deliverables:**

| File | Purpose |
|---|---|
| `analyzers/qa_analyzers.py` | Five analyzer callables conforming to the core pipeline contract |
| `cardiodev_guard/auditors/qa_audit.py` | Injection adapter: feeds `AuditResult` objects into the scanner |
| `tests/test_missing_values.py` | Unit tests for `analyze_missing_values()` |
| `tests/test_duplicates.py` | Unit tests for `analyze_duplicates()` |
| `tests/test_imbalance.py` | Unit tests for `analyze_class_imbalance()` |
| `tests/test_leakage.py` | Unit tests for `analyze_leakage()` |
| `tests/test_model_metrics.py` | Unit tests for `analyze_model_metrics()` |
| `tests/test_qa_adapter.py` | Integration tests for the QA adapter ↔ scanner path |

---

## 2. Quality Checks Performed

The five analyzer functions implement 11 distinct automated checks across two
categories: data quality and model performance.

### Data Quality Checks

| Check | Threshold | Severity raised |
|---|---|---|
| Partial missing values — one or more NaN in a column | Any column with ≥ 1 NaN | `HIGH` |
| Fully-null column — entire column is NaN | `df[col].isnull().all()` is True | `CRITICAL` |
| Moderate duplicate rows | Duplicate fraction < 50 % | `HIGH` |
| Severe duplicate rows | Duplicate fraction ≥ 50 % | `CRITICAL` |
| Mild class imbalance | Minority fraction < 20 % | `HIGH` |
| Severe class imbalance | Minority fraction < 5 % | `CRITICAL` |
| Data leakage (feature–target correlation) | \|Pearson corr\| ≥ 0.95 | `CRITICAL` |
| File-read error on any CSV | Exception during `pd.read_csv()` | `HIGH` |

### Model Performance Checks

| Check | Threshold | Severity raised |
|---|---|---|
| Low ROC-AUC (below minimum acceptable) | ROC-AUC < 0.60 | `HIGH` |
| Below-chance ROC-AUC | ROC-AUC < 0.50 | `CRITICAL` |
| Model load or evaluation failure | Exception during `joblib.load()` or `predict_proba()` | `HIGH` |

### Integration Check

| Check | Evidence |
|---|---|
| QA BLOCKER finding propagates to `ScanReport.release_ready = False` | `TestScannerQualityIndicators::test_qa_blocker_makes_report_not_release_ready` |

**Total distinct automated checks: 11** data/model checks + 1 integration
check = **12 verifiable behavioural guarantees**.

---

## 3. Test Results

**Test run: 125 passed, 0 failed, 0 errors — in 3.03 seconds**  
Platform: Python 3.14.5 on Windows 10 x64  
Source: `docs/impact.md` §3 and grep of `def test_` across `tests/`

| Test module | Tests defined | Domain |
|---|---|---|
| `tests/test_missing_values.py` | 16 | Missing value detection |
| `tests/test_duplicates.py` | ~14 | Duplicate row detection |
| `tests/test_imbalance.py` | ~19 | Class imbalance detection |
| `tests/test_leakage.py` | ~19 | Data leakage detection |
| `tests/test_model_metrics.py` | ~19 | Model metric evaluation |
| `tests/test_qa_adapter.py` | 29 | QA adapter + scanner integration |
| **Total** | **125** | |

> Note: Per-module counts above are indicative; the confirmed total is 125,
> verified by grep of `def test_` across all six modules.

---

## 4. Passed Checks

All 125 tests passed. The following behavioural guarantees are verified:

| Guarantee verified | Test name |
|---|---|
| Partial NaN → `HIGH` severity | `TestOneNaN::test_severity_is_high_for_partial_nan` |
| Fully-null column → `CRITICAL` severity | `TestAllNullColumn::test_entirely_null_column_is_critical` |
| `entirely_null_cols` populated in `raw_data` | `TestAllNullColumn::test_entirely_null_cols_listed_in_raw_data` |
| Moderate duplicate fraction → `HIGH` | `TestOneDuplicate::test_severity_is_high` |
| ≥ 50 % duplicate fraction → `CRITICAL` | `TestAllDuplicates::test_all_dups_severity_critical` |
| Minority fraction 5–20 % → `HIGH` | `TestMildImbalance::test_severity_is_high_for_mild` |
| Minority fraction < 5 % → `CRITICAL` | `TestSevereImbalance::test_severity_is_critical_for_severe` |
| Perfect feature–target correlation → `CRITICAL` leakage | `TestPerfectLeakage::test_finding_severity_critical` |
| ROC-AUC below 0.60 → `HIGH` finding | `TestBadModel::test_roc_auc_value_below_threshold` |
| File-read error → finding, not exception | `TestErrorHandling` classes across all five analyzer test modules |
| Nonexistent file → finding, not exception | `TestUnreadableFile::test_nonexistent_file_produces_finding_not_exception` |
| QA BLOCKER → `ScanReport.release_ready = False` | `TestScannerQualityIndicators::test_qa_blocker_makes_report_not_release_ready` |
| QA BLOCKER → `release_status_label` contains "NOT READY" | `TestScannerQualityIndicators::test_qa_blocker_release_status_label` |
| QA WARNING only → `release_ready = True` | `TestScannerQualityIndicators::test_qa_warning_only_is_release_ready` |
| Injection round-trip preserves severity, title, domain | `TestQaAuditAdapter::test_injected_severity_preserved`, `test_injected_title_preserved`, `test_injected_domain_is_qa` |
| `inject_results(None)` resets adapter state | `TestQaAuditAdapter::test_inject_none_resets_to_empty_result` |
| Adapter does not raise on nonexistent path | `TestQaAuditAdapter::test_run_accepts_nonexistent_path_no_error` |
| `AuditResult.blockers`, `.warnings`, `.passes` filter correctly | Three property tests in `TestQaAuditAdapter` |
| `ScanReport` includes QA domain | `TestScannerQualityIndicators::test_scan_report_includes_qa_domain` |
| Scan timestamp is populated | `TestScannerQualityIndicators::test_scan_timestamp_is_set` |

---

## 5. Warnings and Limitations

The following limitations are acknowledged and documented in `docs/impact.md`:

1. **No `.pkl` model file present in the project root or `phase 2/` directory.**
   The `analyze_model_metrics()` function is fully tested in isolation using
   synthetic models generated in `tmp_path`. However, an end-to-end pipeline
   run against `framingham.csv` with a real trained model has not been
   executed. Actual model finding output (ROC-AUC values, pass/fail status)
   is not available as evidence.

2. **Wall-clock time for manual vs automated review not measured.**
   `docs/impact.md` explicitly marks both timings as `⚠ PLACEHOLDER — must
   be measured`. The only confirmed runtime is the test suite: 3.03 seconds
   for 125 tests.

3. **Actual pipeline findings on `framingham.csv` not recorded.**
   The `framingham.csv` file is present in the project root but the pipeline
   has not been run against it with a model. The before/after finding list
   comparison in `docs/impact.md` §5 is marked as a placeholder.

4. **Imbalance threshold tuned for `TenYearCHD`.**
   The `TARGET_COLUMN` constant is hard-coded to `"TenYearCHD"`. Datasets
   with a different target column name will be silently skipped by
   `analyze_class_imbalance()` and `analyze_leakage()`.

5. **`analyze_leakage()` uses Pearson correlation only.**
   Non-linear relationships between features and the target will not be
   detected by the current threshold-based approach.

---

## 6. Critical Findings

No critical defects were found in the QA-domain codebase during this review.

Evidence reviewed:
- All 125 unit and integration tests pass.
- Every error path in all five analyzers catches exceptions and returns a
  `HIGH`-severity finding rather than propagating the exception — confirmed
  by dedicated `TestErrorHandling` / `TestUnreadableFile` classes in each
  test module.
- The adapter isolation tests (`TestQaAuditAdapter`) confirm that state is
  not leaked between test runs via the `inject_results(None)` teardown
  fixture.
- No test failures, no suppressed exceptions, and no known regressions on
  the Vanshika branch.

---

## 7. Evidence References

| Claim | File / location |
|---|---|
| 125/125 tests passed, 3.03 s, Python 3.14.5 Windows x64 | `docs/impact.md` §3 |
| Five analyzer function signatures and thresholds | `analyzers/qa_analyzers.py` lines 52–58, 63–373 |
| 11 distinct automated checks | `docs/impact.md` §4 |
| Test class and method names | `tests/test_missing_values.py`, `tests/test_duplicates.py`, `tests/test_imbalance.py`, `tests/test_leakage.py`, `tests/test_model_metrics.py` |
| Adapter injection / reset contract | `tests/test_qa_adapter.py` `TestQaAuditAdapter` |
| Scanner integration: BLOCKER → `release_ready = False` | `tests/test_qa_adapter.py` `TestScannerQualityIndicators` |
| `run_scan()` adapter loop and error surfacing | `cardiodev_guard/scanner.py` lines 60–83 |
| Manual-vs-automated workflow comparison | `docs/impact.md` §§1–2 |
| Placeholders for unrecorded measurements | `docs/impact.md` §§3, 5, "Placeholders" table |

---

## 8. Recommendations

1. **Run the pipeline against `framingham.csv` with a trained `.pkl` model.**
   Place or train a model, then execute `run_pipeline(".", [...])` and record
   the full finding list and `output.summary`. This closes the placeholder
   in `docs/impact.md` §5 and produces the concrete before/after comparison.

2. **Record wall-clock timing for both manual and automated review.**
   Time a manual pass of `framingham.csv` (all five checks) and the elapsed
   time of a single `run_pipeline()` call on the same machine with the same
   dataset, then update `docs/impact.md` §3.

3. **Extend `TARGET_COLUMN` to accept a parameter or configuration value.**
   The hard-coded `"TenYearCHD"` default limits reuse on datasets with
   different target column names. Existing tests already pass a
   `target_column` argument, so the function signature already supports it.

4. **Consider adding a non-linear leakage detector.**
   The current Pearson-only approach will miss monotonic but non-linear
   relationships. A mutual-information or Spearman-rank supplement would
   increase coverage.

5. **Add end-to-end integration test with real CSV.**
   The existing tests use `tmp_path` synthetic data. A test that loads
   `framingham.csv` directly would provide a regression anchor against the
   actual dataset characteristics.

---

## 9. Quality Indicators

| Indicator | Value | Source |
|---|---|---|
| Total tests defined | 125 | `tests/` — grep of `def test_` |
| Tests passed | 125 | `docs/impact.md` §3 |
| Tests failed | 0 | `docs/impact.md` §3 |
| Test runtime | 3.03 seconds | `docs/impact.md` §3 |
| Distinct automated checks implemented | 11 | `docs/impact.md` §4; `analyzers/qa_analyzers.py` |
| Analyzer functions | 5 | `analyzers/qa_analyzers.py` |
| Error paths with exception handling | ≥ 5 (one per analyzer) | `TestUnreadableFile` / `TestErrorHandling` in each test module |
| Adapter state-isolation verified | Yes | `test_inject_none_resets_to_empty_result` |
| Release gate integration verified | Yes | `TestScannerQualityIndicators` (14 tests) |
| Known failing tests | 0 | |
| Unresolved BLOCKER defects | 0 | |
| Placeholders requiring real measurement | 3 | `docs/impact.md` "Placeholders" table |

---

## 10. Release Readiness

**QA-domain code and tests: READY FOR REVIEW — conditional on resolving placeholders.**

**Basis for this assessment (evidence-only):**

- All 125 tests pass with 0 failures and 0 errors on the Vanshika branch.
- All five analyzer functions handle file-read and evaluation errors
  gracefully without propagating exceptions.
- The release-gate integration path is verified end-to-end: a QA BLOCKER
  finding correctly sets `ScanReport.release_ready = False` and
  `release_status_label` to "NOT READY FOR RELEASE".
- No critical defects were identified during this review.

**Conditions that must be met before a full project release decision:**

1. The wall-clock timing placeholders in `docs/impact.md` §3 must be
   measured and recorded.
2. The pipeline must be run against `framingham.csv` with a trained model
   and the actual finding list must be recorded in `docs/impact.md` §5.
3. If the actual pipeline run produces any `CRITICAL` or `BLOCKER` findings
   on the real dataset, those findings must be triaged before release.

The QA-domain implementation itself — the five analyzers, the adapter, and
the test suite — is complete and verified by the 125-test run.
