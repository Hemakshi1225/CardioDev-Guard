# CardioDev Guard — Core Architecture Plan (Tanish)

## Top-Level Overview

**Goal:** Build the core backbone of CardioDev Guard — the project loader, orchestration pipeline,
findings aggregator, issue explainer, and structured output contracts that all other teammates plug into.

**Scope (Tanish only):**
- Project input ingestion and validation
- Orchestration of the analysis pipeline
- Shared data models (the contracts between all modules)
- Findings aggregation from teammate analyzers
- Structured issue explanation
- Recommendation generation
- Structured output for UI, report, and test modules

**Non-goals:**
- ML/data analysis logic (teammate)
- Automated test execution (teammate)
- UI rendering (teammate)
- Report generation (teammate)

**Tech stack:** Python 3.10+, standard library only where possible, dataclasses for models,
`pytest` for tests, optional `pydantic` for validation if available.

**Design principle:** Every module is independently importable. No circular dependencies.
Teammates only need to read `core/models.py` to know the contracts.

---

## Repository Layout

```
CardioDev-Guard/
├── core/
│   ├── __init__.py
│   ├── models.py          # All shared data models — THE contract file
│   ├── project_loader.py  # Reads and validates a project directory
│   ├── orchestrator.py    # Drives the full pipeline end-to-end
│   ├── aggregator.py      # Collects and merges analyzer results
│   ├── explainer.py       # Turns raw findings into human-readable explanations
│   └── recommender.py     # Maps findings to actionable recommendations
├── tests/
│   ├── test_models.py
│   ├── test_project_loader.py
│   ├── test_orchestrator.py
│   ├── test_aggregator.py
│   ├── test_explainer.py
│   └── test_recommender.py
├── requirements.txt
└── README.md              # (already exists — update with usage instructions)
```

---

## Sub-Tasks

---

### Sub-Task 1 — Shared Data Models (`core/models.py`)

**Intent**
Define every data structure that crosses a module boundary. This is the single source of truth
for how data flows through the entire system. Teammates read this file to know what to produce
and what to consume. All other sub-tasks depend on this file existing first.

**Expected Outcomes**
- `core/models.py` exists and is importable
- Every model is a Python `dataclass` with type annotations
- Models cover: project input, analysis request, analyzer result, finding, recommendation, structured output
- The file has clear docstrings so teammates can understand the contract without asking

**Todo List**
1. Create `core/__init__.py` (empty)
2. Create `core/models.py` with the following dataclasses:
   - `ProjectInput` — path, name, optional metadata dict
   - `AnalysisRequest` — derived from ProjectInput; includes discovered file paths by category
     (model files, data files, test files, source files, docs)
   - `Finding` — severity enum (CRITICAL/HIGH/MEDIUM/LOW/INFO), category string,
     title, description, file_path (optional), line_number (optional), raw_data dict
   - `AnalyzerResult` — analyzer_name string, list of Findings, success bool, error_message (optional)
   - `Recommendation` — linked to a Finding via finding id, action_title, detail, priority int
   - `StructuredOutput` — the final object handed to UI/report/test modules;
     contains: project_name, analysis_request, list of AnalyzerResults, list of Findings
     (aggregated), list of Recommendations, overall_status enum (READY/NEEDS_WORK/CRITICAL),
     summary string, timestamp
3. Add a `Severity` IntEnum and `OverallStatus` Enum to the same file
4. Write module-level docstring explaining the contract

**Relevant Context**
- No existing code to reference — this is the foundation
- Keep models serializable: use only stdlib types inside dataclasses
  (str, int, float, bool, list, dict, Optional, None — no custom objects nested inside)

**Status:** [x] done

---

### Sub-Task 2 — Project Loader (`core/project_loader.py`)

**Intent**
Accept a filesystem path to a user's ML project, validate that it is a real directory,
walk the tree to discover relevant files (by extension/name pattern), and produce an
`AnalysisRequest` that the orchestrator will pass to analyzers.

**Expected Outcomes**
- `core/project_loader.py` exports a single public function `load_project(path: str) -> AnalysisRequest`
- Raises a clear `ValueError` if the path does not exist or is not a directory
- Categorises discovered files into: model files (.pkl, .h5, .pt, .joblib, .onnx),
  data files (.csv, .json, .parquet, .xlsx), test files (files/dirs named test_* or *_test.py),
  source files (.py), docs (.md, .txt, .rst)
- Returns a valid `AnalysisRequest` with all discovered paths populated

**Todo List**
1. Create `core/project_loader.py`
2. Implement `load_project(path: str) -> AnalysisRequest`
   - Validate path exists and is a directory; raise `ValueError` with a clear message if not
   - Walk the directory tree using `os.walk`, skipping `.git`, `__pycache__`, `.venv`, `node_modules`
   - Categorise files into the five buckets by extension and naming convention
   - Construct and return `AnalysisRequest`
3. Add module docstring explaining purpose and usage

**Relevant Context**
- Depends on: `core/models.py` (Sub-Task 1)
- Teammates' analyzers receive the `AnalysisRequest` — the file path lists in it are how they
  know what to look at

**Status:** [ ] pending

---

### Sub-Task 3 — Findings Aggregator (`core/aggregator.py`)

**Intent**
Accept a list of `AnalyzerResult` objects (one per teammate analyzer) and merge them into a
single flat, de-duplicated, severity-sorted list of `Finding` objects. This is the normalisation
layer — it doesn't care which analyzer produced a finding.

**Expected Outcomes**
- `core/aggregator.py` exports `aggregate(results: list[AnalyzerResult]) -> list[Finding]`
- Findings are sorted: CRITICAL first, INFO last
- Duplicate findings (same category + title + file_path) are collapsed into one
- Findings from analyzers that returned `success=False` are still included if present;
  a synthetic CRITICAL finding is added when an analyzer failed with an error message
- Empty input returns an empty list without error

**Todo List**
1. Create `core/aggregator.py`
2. Implement `aggregate(results: list[AnalyzerResult]) -> list[Finding]`
   - Iterate each `AnalyzerResult`
   - For failed results with an error message, inject a CRITICAL Finding summarising the failure
   - Flatten all findings into one list
   - Remove duplicates by (category, title, file_path) key — keep highest severity copy
   - Sort by `Severity` descending (CRITICAL → INFO)
3. Add module docstring

**Relevant Context**
- Depends on: `core/models.py` (Sub-Task 1)
- Output feeds directly into Sub-Task 4 (Explainer) and Sub-Task 5 (Recommender)

**Status:** [x] done

---

### Sub-Task 4 — Issue Explainer (`core/explainer.py`)

**Intent**
Transform each raw `Finding` into a richer, human-readable explanation — what the issue is,
why it matters for ML project quality, and what the impact could be. This is the "structured
issue explanation" responsibility. It works from a static rule table, not an external API,
to keep it dependency-free and fast.

**Expected Outcomes**
- `core/explainer.py` exports `explain(findings: list[Finding]) -> list[Finding]`
- Returns the same `Finding` objects with their `description` field enriched/replaced
  by a clear explanation (if the explainer has a rule for that category)
- Findings whose category has no rule are returned unchanged
- The rule table covers at minimum these categories: data_quality, model_performance,
  test_coverage, documentation, dependency, code_quality
- No external API calls — all explanations are template strings in the rule table

**Todo List**
1. Create `core/explainer.py`
2. Define an internal `EXPLANATION_RULES` dict mapping category strings to explanation templates
   - Each template is a string that can reference `{title}` and `{severity}` via `.format()`
   - Cover at minimum: data_quality, model_performance, test_coverage,
     documentation, dependency, code_quality, analyzer_failure
3. Implement `explain(findings: list[Finding]) -> list[Finding]`
   - For each finding, look up its category in `EXPLANATION_RULES`
   - If found, overwrite `description` with the rendered template
   - Return the list (mutate in place or return new list — be consistent)
4. Add module docstring

**Relevant Context**
- Depends on: `core/models.py` (Sub-Task 1)
- Input comes from aggregator output (Sub-Task 3)

**Status:** [x] done

---

### Sub-Task 5 — Recommendation Engine (`core/recommender.py`)

**Intent**
Map each `Finding` to one or more concrete `Recommendation` objects — specific actions the
developer can take. Works from a static rule table keyed on (category, severity). Keeps it
simple and hackathon-appropriate.

**Expected Outcomes**
- `core/recommender.py` exports `recommend(findings: list[Finding]) -> list[Recommendation]`
- Every CRITICAL and HIGH finding gets at least one recommendation
- Recommendations are sorted by priority (1 = most urgent)
- Findings with no matching rule get a generic fallback recommendation
- No external API calls

**Todo List**
1. Create `core/recommender.py`
2. Define internal `RECOMMENDATION_RULES` dict mapping (category, severity) tuples to
   recommendation templates (action_title + detail strings)
   - Cover the same categories as the explainer (data_quality, model_performance,
     test_coverage, documentation, dependency, code_quality, analyzer_failure)
3. Implement `recommend(findings: list[Finding]) -> list[Recommendation]`
   - For each finding, look up (category, severity) in rules
   - Fall back to (category, None) then to a generic rule if no match
   - Assign priority based on severity (CRITICAL=1, HIGH=2, MEDIUM=3, LOW=4, INFO=5)
   - Return sorted list
4. Add module docstring

**Relevant Context**
- Depends on: `core/models.py` (Sub-Task 1)
- Input is the explained findings from Sub-Task 4

**Status:** [x] done

---

### Sub-Task 6 — Orchestrator (`core/orchestrator.py`)

**Intent**
Wire the entire pipeline together into a single callable. The orchestrator is what the final
application entry point will call. It accepts a project path and a list of analyzer callables
(provided by teammates), runs them, and returns a `StructuredOutput`.

**Expected Outcomes**
- `core/orchestrator.py` exports `run_pipeline(project_path: str, analyzers: list[callable]) -> StructuredOutput`
- Pipeline order: load → analyze → aggregate → explain → recommend → package output
- Each analyzer callable receives an `AnalysisRequest` and returns an `AnalyzerResult`
- If an analyzer raises an exception, it is caught, logged to stderr, and a failed
  `AnalyzerResult` is created for it — the pipeline continues with remaining analyzers
- Returns a complete `StructuredOutput` even if some analyzers fail
- `overall_status` is computed from the aggregated findings:
  any CRITICAL → CRITICAL; any HIGH → NEEDS_WORK; otherwise → READY
- `summary` is a one-paragraph plain-English string summarising the counts

**Todo List**
1. Create `core/orchestrator.py`
2. Implement `run_pipeline(project_path: str, analyzers: list[callable]) -> StructuredOutput`
   - Call `load_project(project_path)` → get `AnalysisRequest`
   - Loop through each analyzer callable, call it with `AnalysisRequest`,
     catch any exception and convert to a failed `AnalyzerResult`
   - Call `aggregate(analyzer_results)` → flat `list[Finding]`
   - Call `explain(findings)` → enriched findings
   - Call `recommend(findings)` → `list[Recommendation]`
   - Compute `overall_status` from findings
   - Build and return `StructuredOutput`
3. Add module docstring with example usage snippet (comment block)

**Relevant Context**
- Depends on: all previous sub-tasks
- This is the entry point teammates call. The function signature `run_pipeline(path, analyzers)`
  must not change without coordinating with the team.
- Teammates register their analyzers as callables: `def my_analyzer(req: AnalysisRequest) -> AnalyzerResult`

**Status:** [x] done

---

### Sub-Task 7 — `requirements.txt` and package setup

**Intent**
Make the project installable and establish the dependency baseline so all teammates use
the same Python version and optional libraries.

**Expected Outcomes**
- `requirements.txt` created with pinned versions for: `pytest`, optional `pydantic` if chosen
- Python version documented (3.10+)
- `core/` is importable without installation (can run from repo root)

**Todo List**
1. Create `requirements.txt` with at minimum: `pytest>=7.0`
2. Update `README.md` with:
   - Project overview (expand existing one-liner)
   - How to run the pipeline
   - How teammates register their analyzers
   - How to run tests

**Relevant Context**
- Keep dependencies minimal — this is a hackathon project

**Status:** [x] done

---

### Sub-Task 8 — Tests

**Intent**
Write unit tests for all five core modules. Tests serve as working documentation for teammates
and catch regressions during integration. Each test file is independent.

**Expected Outcomes**
- `tests/` directory with one test file per module
- `pytest` runs all tests with `pytest tests/` from repo root
- Tests cover: happy path, edge cases (empty input, bad path), failure modes
- No external dependencies in tests (no real ML project needed — use temp directories and
  mock `AnalyzerResult` objects)

**Todo List**
1. Create `tests/__init__.py` (empty)
2. `tests/test_models.py` — instantiate each dataclass; verify field defaults; verify Severity ordering
3. `tests/test_project_loader.py` — use `tempfile.TemporaryDirectory` to create a fake project;
   test valid path, invalid path (ValueError), empty directory, mixed file types
4. `tests/test_aggregator.py` — test deduplication, severity sorting, failed analyzer injection,
   empty input
5. `tests/test_explainer.py` — test known category enrichment, unknown category passthrough,
   empty input
6. `tests/test_recommender.py` — test CRITICAL gets priority-1 recommendation, fallback rule,
   empty input
7. `tests/test_orchestrator.py` — test full pipeline with two mock analyzers (one succeeding,
   one raising an exception); verify StructuredOutput is always returned

**Relevant Context**
- Depends on: all sub-tasks 1–6 complete
- Use `unittest.mock` or simple lambda/closure stubs for mock analyzers — no extra libraries needed

**Status:** [x] done

---

## Interface Contracts for Teammates

### How a teammate registers an analyzer

```
# Teammate's analyzer must match this signature exactly:
def my_analyzer(request: AnalysisRequest) -> AnalyzerResult:
    ...

# Registration at the entry point:
from core.orchestrator import run_pipeline
from core.models import StructuredOutput

output: StructuredOutput = run_pipeline(
    project_path="./my_ml_project",
    analyzers=[ml_analyzer, test_analyzer]
)
```

### How UI / Report teammates consume output

```
from core.models import StructuredOutput, OverallStatus

# output is a StructuredOutput instance
output.overall_status   # OverallStatus.READY | NEEDS_WORK | CRITICAL
output.findings         # list[Finding] — sorted by severity
output.recommendations  # list[Recommendation] — sorted by priority
output.summary          # plain English paragraph
output.project_name     # str
output.timestamp        # str (ISO 8601)
```

### Finding categories (agreed vocabulary)

| Category            | Who produces it          |
|---------------------|--------------------------|
| `data_quality`      | ML/data analyzer teammate |
| `model_performance` | ML/data analyzer teammate |
| `test_coverage`     | Test analyzer teammate    |
| `documentation`     | Test analyzer teammate    |
| `dependency`        | Test analyzer teammate    |
| `code_quality`      | Test analyzer teammate    |
| `analyzer_failure`  | Orchestrator (auto)      |

Teammates MUST use one of these category strings in their `Finding` objects.
New categories can be added by updating `core/models.py` and `core/explainer.py` together.

---

## Error Handling Strategy

| Scenario | Handling |
|----------|----------|
| Project path does not exist | `ValueError` raised by `project_loader`, propagates to caller |
| Analyzer raises an unhandled exception | Caught by orchestrator; synthetic CRITICAL finding created; pipeline continues |
| No files found of a given type | Empty list in `AnalysisRequest`; analyzers handle gracefully |
| All analyzers fail | `StructuredOutput` returned with CRITICAL status and explanation |
| Empty findings list | `StructuredOutput` returned with READY status |

---

## Data Flow Summary

```
project_path (str)
    └─> project_loader.load_project()
            └─> AnalysisRequest
                    ├─> analyzer_1(AnalysisRequest) -> AnalyzerResult
                    ├─> analyzer_2(AnalysisRequest) -> AnalyzerResult
                    └─> [more analyzers...]
                            └─> aggregator.aggregate([AnalyzerResult, ...])
                                    └─> list[Finding]
                                            └─> explainer.explain(list[Finding])
                                                    └─> list[Finding] (enriched)
                                                            └─> recommender.recommend(list[Finding])
                                                                    └─> list[Recommendation]
                                                                            └─> StructuredOutput
                                                                                    ├─> UI module
                                                                                    ├─> Report module
                                                                                    └─> Test runner
```
