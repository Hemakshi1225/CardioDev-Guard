# CardioDev-Guard — Final Quality Report

**Branch:** Hemakshi  
**Reference commit:** e896233  
**Date:** 2026-09-26  
**Test suite:** 254 passed, 0 failed

---

## 1. Project Overview

CardioDev-Guard is a Streamlit developer dashboard that audits local ML projects for
data-quality, model-performance, and release-readiness issues.  It implements a
Scan → Analyze → Report → Re-check workflow and produces graded findings
(BLOCKER / WARNING / PASS) across three audit domains: ML, QA, and Release.

**Repository:** CardioDev-Guard (this repository)  
**Target project for live validation:** `/Users/macbookair/Desktop/ME228_PROJECT`  
These are distinct: the dashboard can target any local ML project directory;
the CardioDev-Guard repo itself is the default target for the built-in demo.

---

## 2. Architecture

```
dashboard.py                        ← Streamlit UI; target-project selection
  │
  ├─ cardiodev_guard/scanner.py     ← Scan orchestration; calls all adapters
  │     ├─ auditors/ml_audit.py     ← ML domain adapter (Tanish core bridge)
  │     ├─ auditors/qa_audit.py     ← QA domain adapter + finding consolidation
  │     └─ auditors/release_audit.py← Release domain adapter (pending)
  │
  ├─ cardiodev_guard/core_bridge.py ← Translates core findings → dashboard findings
  │     └─ core/ (Tanish)           ← Pipeline: load → analyze → aggregate → explain → recommend
  │
  └─ analyzers/qa_analyzers.py      ← Five QA analyzer callables (Vanshika)
```

**Invariants:**
- `core/` modules are read-only; no changes to Tanish's contracts.
- Analyzer logic lives only in `analyzers/qa_analyzers.py`; it is not duplicated.
- `logistic_model.pkl` and ML training/prediction files are not modified.

---

## 3. Severity Classification

### Core → Dashboard mapping (via `core_bridge._SEVERITY_MAP`)

| Core `Severity` | Dashboard `Severity` | Effect on release gate |
|---|---|---|
| CRITICAL | **BLOCKER** | NOT READY |
| HIGH | **BLOCKER** | NOT READY |
| MEDIUM | **WARNING** | Does not block release |
| LOW | **WARNING** | Does not block release |
| INFO | **PASS** | Does not block release |

### Class imbalance severity ladder

| Minority fraction | Core severity | Dashboard severity | Rationale |
|---|---|---|---|
| ≥ 20 % | No finding | — | Balanced enough |
| 5 – 20 % | MEDIUM | **WARNING** | Common in medical datasets; warrants review |
| < 5 % | HIGH | **BLOCKER** | Extreme; model likely defaults to majority class |

The 15.2 % TenYearCHD minority ratio observed in the Framingham dataset falls in the
5–20 % band and is therefore classified as **WARNING**, not BLOCKER.

This corrects the previous behaviour where any imbalance below 20 % was `HIGH` → BLOCKER
regardless of magnitude, which produced spurious blockers for a well-known characteristic
of medical outcome data.

The `IMBALANCE_CRITICAL_THRESHOLD` constant is preserved as an alias for
`IMBALANCE_HIGH_THRESHOLD` (= 0.05) so existing code that references it continues to work.

---

## 4. Finding Descriptions

All finding descriptions are now evidence-specific rather than generic:

| Analyzer | Description now includes |
|---|---|
| Missing values (partial) | Exact count, affected column names, percentage of total cells, imputation guidance |
| Missing values (entirely null) | Column names that are entirely NaN, specific note that they cannot be used for training |
| Model load failure | `joblib.load()` exception type and message, note about corrupt/incompatible artifact, remediation hint |
| Model eval failure | `predict()` / `predict_proba()` exception type and message, note that this is concrete evidence the model cannot score the dataset |
| Low ROC-AUC | Actual AUC and accuracy values, threshold, specific note if AUC < 0.50 (worse than random) |

---

## 5. Finding Consolidation

Implemented in `cardiodev_guard/auditors/qa_audit._deduplicate_findings()`.

### Algorithm

1. For each dashboard finding, compute `issue_stem(title)` by stripping any trailing
   `" in <filename.ext>"` or `" for <filename.ext>"` via a regex.
2. Group findings by `(category, issue_stem)`.
3. For groups with more than one member:
   - **Title:** `"<stem> [N file(s)]"`
   - **Severity:** highest in the group
   - **Evidence:** all per-file evidence blocks, numbered `[1/N] … [2/N] …`
   - **Explanation / fix / validation:** from the highest-severity member
   - **`extra.deduplicated_from`:** count of merged findings
4. Groups with a single member are returned unchanged.
5. Original relative ordering (first occurrence of each group) is preserved.

### Example

Three CSV copies of the same dataset all have missing values:

```
Before: 3 separate BLOCKER findings
  "Missing values detected in framingham.csv"
  "Missing values detected in phase2/framingham.csv"
  "Missing values detected in phase3/framingham.csv"

After: 1 BLOCKER finding
  "Missing values detected [3 file(s)]"
  Evidence:
    [1/3] File: /path/framingham.csv; missing_count: 582; …
    [2/3] File: /path/phase2/framingham.csv; missing_count: 582; …
    [3/3] File: /path/phase3/framingham.csv; missing_count: 582; …
```

### Limitation

Findings whose titles do not end with a recognised file-extension suffix are not
stem-stripped.  This includes class-imbalance findings:

```
"Class imbalance detected in TenYearCHD (15.2% minority)"
```

Because this title contains no file extension, `issue_stem` returns it unchanged.
If two dataset files produce the identical title (same ratio, same column), they will
be merged by exact title equality — which is correct.  If two files produce different
ratios, they produce different titles and appear as separate findings.  A human reviewer
should confirm whether they represent the same underlying dataset distribution.

---

## 6. Generic Target-Project Validation

The dashboard accepts any local ML project directory as the scan target.

| Behaviour | Detail |
|---|---|
| Default target | CardioDev-Guard repository (`Path(__file__).resolve().parent`) |
| Custom target | Any absolute path entered in "Local ML project folder path" |
| Path validation | `_resolve_target()` checks existence and `is_dir()`; surfaces `st.error()` on failure |
| Spaces in paths | Supported — `pathlib.Path` used throughout |
| Leading/trailing whitespace | Stripped before validation |
| Session persistence | `key="target_project_path"` in `st.text_input`; both Run Scan and Re-check read from `st.session_state` |
| Re-check behaviour | Uses the currently entered target path (whatever the user has in the input field at click time) |

---

## 7. Live Scan — ME228\_PROJECT Validation

A scan of `/Users/macbookair/Desktop/ME228_PROJECT` on 2026-09-26 produced:

| Metric | Result |
|---|---|
| Total findings | 10 |
| BLOCKER | 5 |
| WARNING | 5 |
| PASS | 0 |
| Release status | **NOT READY** |

This project is not READY and is not claimed to be.  The BLOCKER findings represent
concrete, evidence-backed issues.  The WARNING findings include the consolidated
class-imbalance signals (now correctly WARNING rather than BLOCKER).

---

## 8. Release-Readiness Logic

```
ScanReport.release_ready = (len(blockers across all domains) == 0)

READY FOR RELEASE        → no BLOCKER findings in ML + QA + Release domains
NOT READY — BLOCKERS PRESENT → one or more BLOCKER findings exist
```

This is a **developer quality and release-readiness signal** produced by the configured
set of analyzers.  It is not a substitute for domain-specific human validation, clinical or
regulatory review, model fairness assessment, or security audit.

A READY verdict from this tool should be treated as a necessary but not sufficient
condition for deployment.

---

## 9. Test Evidence

### Summary

| Test file | Tests | Covers |
|---|---|---|
| `test_aggregator.py` | 16 | Core aggregator: dedup, severity sort, failure injection |
| `test_explainer.py` | 36 | Core explainer: known/unknown categories, template substitution |
| `test_integration.py` | 54 | Bridge translation, scanner, adapters, path selection, release-ready logic |
| `test_models.py` | 37 | Core data models: severity ordering, dataclass defaults |
| `test_orchestrator.py` | 28 | Full pipeline: crash recovery, status computation, summary |
| `test_project_loader.py` | 22 | File discovery, path validation, ignored directories |
| `test_qa_severity_dedup.py` | 29 | QA severity ladder, descriptions, `_issue_stem`, `_deduplicate_findings` |
| `test_recommender.py` | 32 | Recommendation rules, priority mapping, fallbacks |
| **Total** | **254** | |

### Run command

```bash
python -m pytest tests/ -v
```

### Result

```
254 passed, 0 failed  (2026-09-26, Python 3.14.6, pytest 9.0.3)
```

### New tests added on this branch (`test_qa_severity_dedup.py` — 29 tests)

| Class | Tests | What is verified |
|---|---|---|
| `TestClassImbalanceSeverity` | 8 | MEDIUM for 5–20 %, HIGH for < 5 %, boundary at exactly 5 %, alias preservation |
| `TestMissingValueDescriptions` | 2 | Specific description content for partial and entirely-null cases |
| `TestModelMetricsDescriptions` | 2 | Specific description content for load failure and eval failure |
| `TestIssueStem` | 7 | `_issue_stem()`: CSV/PKL/parquet stripping, unchanged titles, empty string |
| `TestDeduplicateFindings` | 10 | Grouping, evidence merge, severity escalation, ordering, edge cases |

---

## 10. Limitations

| Issue | Status | Guidance |
|---|---|---|
| Class imbalance at exactly 5 % | WARNING (boundary) | If model confusion matrix shows poor minority recall, upgrade manually to BLOCKER |
| Different minority ratios in different files | Separate findings (not merged) | Confirm whether files are copies of the same dataset or genuinely different distributions |
| Model load failure | BLOCKER (correct) | Re-train the model and re-export with matching scikit-learn version |
| Duplicate rows in intentional splits | BLOCKER finding | If phase2/phase3 are intentional train/test splits, duplicate rows are expected; dismiss manually |
| Leakage threshold (Pearson ≥ 0.95) | BLOCKER if triggered | If a high-correlation feature is a legitimate composite (not leakage), dismiss manually |
| Release domain | Pending (empty) | Release-team adapter not yet integrated; release domain always shows "awaiting results" |
| Manual baseline | Not measured | A controlled manual audit time baseline was not collected; time-saving claims would be unsupported |

---

## 11. Files Changed on Hemakshi Branch

| File | Change |
|---|---|
| `analyzers/qa_analyzers.py` | Severity ladder for class imbalance; specific descriptions for all finding types |
| `cardiodev_guard/auditors/qa_audit.py` | Added `_issue_stem()`, `_deduplicate_findings()`, `run()`, `inject_results()` |
| `dashboard.py` | QA analyzer registration; "Target ML Project" section; `_resolve_target()` helper |
| `tests/test_integration.py` | Updated stale assumptions; added `TestTargetPathSelection` (9 tests) |
| `tests/test_qa_severity_dedup.py` | New file: 29 tests for severity and deduplication |
| `docs/impact.md` | New file (this report's companion) |
| `docs/final_quality_report.md` | New file (this document) |

**Unchanged:** `core/`, `logistic_model.pkl`, all ML training and prediction files,
`cardiodev_guard/scanner.py`, `cardiodev_guard/core_bridge.py`,
`cardiodev_guard/auditors/ml_audit.py`, `cardiodev_guard/auditors/release_audit.py`.

---

*CardioDev-Guard — Hemakshi branch — 2026-09-26*
