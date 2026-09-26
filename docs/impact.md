# CardioDev-Guard — Impact Summary

**Branch:** Hemakshi  
**Reference commit:** e896233  
**Date:** 2026-09-26

---

## Problem Statement

ML projects accumulate quality debt that is invisible at release time: missing values left
in training data, class imbalance that goes unaddressed, model artifacts that cannot be
loaded, and repeated copies of datasets that flood any audit output with noise.  Manual
review of these issues is inconsistent, depends on individual awareness, and leaves no
audit trail.

CardioDev-Guard addresses this by running a structured, automated audit pipeline against
any local ML project directory.  It emits graded findings (BLOCKER / WARNING / PASS),
consolidates repeated findings across dataset copies, and presents a release-readiness
verdict that the team can act on before deployment.

---

## Before vs After Workflow

| Stage | Before CardioDev-Guard | With CardioDev-Guard |
|---|---|---|
| Data quality check | Manual inspection of CSVs, no standard format | Automated: missing values, duplicates, class imbalance detected and graded |
| Model validation | Run ad-hoc scripts per developer | Automated: load failure and evaluation failure detected with specific error context |
| Duplicate findings from dataset copies | Noise — same issue reported N times | Consolidated: N files → one finding, all file paths listed in evidence |
| Severity calibration | Subjective per reviewer | Defined ladder: 15–20 % class imbalance → WARNING; <5 % → BLOCKER; entirely-null column → BLOCKER |
| Release decision | Informal, no shared signal | Dashboard shows READY / NOT READY based on presence or absence of BLOCKER findings |
| Target flexibility | Hard-coded to one project | Any local ML project directory can be selected from the dashboard |

---

## Automated Checks Implemented

Five analyzers run on every scan of the target project:

| Analyzer | What it checks | Finding category |
|---|---|---|
| Missing Value Analyzer | NaN cells per column in every CSV; entirely-null columns | `data_quality` |
| Duplicate Row Analyzer | Exact duplicate rows per CSV | `data_quality` |
| Class Imbalance Analyzer | Minority-class fraction in `TenYearCHD` (or configurable column) | `data_quality` |
| Model Metrics Analyzer | joblib load success; predict/predict\_proba evaluation; ROC-AUC vs threshold | `model_performance` |
| Leakage Detector | Near-perfect Pearson correlation (≥ 0.95) between any feature and the target | `data_quality` |

All five are registered once at dashboard startup and executed via the shared Tanish core
pipeline (`core.orchestrator.run_pipeline`).  No analyzer logic is duplicated between the
QA module and the core.

---

## Severity Classification

Core pipeline severity levels map to dashboard severity as follows:

| Core severity | Dashboard severity | Meaning |
|---|---|---|
| CRITICAL | **BLOCKER** | Release-blocking; must be resolved |
| HIGH | **BLOCKER** | Release-blocking; must be resolved |
| MEDIUM | **WARNING** | Warrants review; not automatically release-blocking |
| LOW | **WARNING** | Minor concern |
| INFO | **PASS** | Informational only |

### Class imbalance calibration

A 15.2 % minority class in `TenYearCHD` (the Framingham dataset ratio) was previously
classified as `HIGH` → **BLOCKER**, which misrepresented a characteristic of many medical
outcome datasets as a release-blocking defect.

After the severity refinement on this branch:

- **15–20 % minority** → `MEDIUM` → **WARNING** — common in medical datasets; warrants
  review of class weighting or resampling strategy, but is not automatically release-blocking.
- **< 5 % minority** → `HIGH` → **BLOCKER** — extreme imbalance that will cause the model
  to default-predict the majority class; must be addressed before release.

---

## Finding Consolidation

When the same logical issue appears in multiple dataset copies (e.g. `phase2/framingham.csv`
and `phase3/framingham.csv`), the QA audit adapter consolidates them:

- **Grouping key:** `(category, issue_stem)` where `issue_stem` strips any trailing
  `"in <filename.ext>"` or `"for <filename.ext>"` from the finding title.
- **Merged title:** `"Missing values detected [2 file(s)]"`
- **Evidence:** all per-file evidence blocks are retained, numbered `[1/2]`, `[2/2]`, …
- **Severity:** highest severity among the group.

**Limitation:** Findings whose titles do not end with a file-extension suffix — such as
`"Class imbalance detected in TenYearCHD (15.2% minority)"` — share the same title across
files and are merged by title equality rather than by stem stripping.  This is correct
behaviour (it is the same logical issue), but it means that if two dataset files have
different measured minority ratios, the second title would differ and both would appear
separately.  A human reviewer should confirm whether consolidated class-imbalance findings
represent the same underlying dataset or genuinely different distributions.

---

## Validated Against ME228\_PROJECT

A live scan of `/Users/macbookair/Desktop/ME228_PROJECT` on 2026-09-26 produced:

| Metric | Value |
|---|---|
| Total findings | 10 |
| BLOCKER findings | 5 |
| WARNING findings | 5 |
| PASS findings | 0 |
| Release status | **NOT READY** |

The BLOCKER findings represent concrete, evidence-backed issues (model load/evaluation
failures, missing values in critical columns) rather than threshold artefacts.  The WARNING
findings include the consolidated class-imbalance signals that require human review but are
not automatically release-blocking.

This scan validates that the severity refinement and finding consolidation work correctly
against a real project: the class imbalance finding appears as WARNING rather than BLOCKER,
and repeated dataset findings are grouped with all file paths preserved in evidence.

---

## Release-Readiness Signal

The dashboard displays **READY FOR RELEASE** when no BLOCKER findings are present across all
audit domains (ML, QA, Release).  It displays **NOT READY — BLOCKERS PRESENT** when one or
more BLOCKER findings exist.

This is a **developer quality and release-readiness signal**.  It is not a substitute for:
- Domain-specific human validation (clinical, regulatory, or business criteria)
- Model fairness or bias assessments
- Statistical significance or generalisability review
- Security or compliance audits

The release-readiness gate is the configured scanner's assessment based on the implemented
analyzers.  Teams should treat a READY verdict as a necessary but not sufficient condition
for deployment.

---

## Generic Target-Project Support

The dashboard accepts any local ML project directory as a scan target.  The default target
is the CardioDev-Guard repository itself (for the built-in demo).  A user can enter any
absolute path in the "Target ML Project" field.

Path handling:
- Leading and trailing whitespace is stripped.
- Paths containing spaces are supported (`pathlib.Path` is used throughout).
- A non-existent path or a path pointing to a file rather than a directory surfaces a clear
  `st.error()` message without crashing the dashboard.
- The selected path is stored in `st.session_state` so both "Run Scan" and "Re-check" use
  the same target the user last entered.

---

## Note on Time Savings

A controlled manual baseline for the types of checks implemented here was not measured
during this project.  Any specific time-saving figures would be unsupported claims.  The
tool's value is in consistency, repeatability, and providing a shared audit signal across
the team — not in replacing domain expertise.

---

*CardioDev-Guard — Hemakshi branch — 2026-09-26*
