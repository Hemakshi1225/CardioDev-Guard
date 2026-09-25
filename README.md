# CardioDev Guard

AI-powered ML project quality and release-readiness assistant.  
CardioDev Guard analyses datasets, models, tests, and documentation to detect
issues, suggest fixes, and assess whether an ML project is ready to release.

> **Hackathon project** — Built with Python 3.10+ and IBM Bob 2.0.

---

## Requirements

- Python **3.10 or later**
- No third-party runtime dependencies — the `core/` package uses the standard library only
- `pytest>=7.0` for running tests (dev dependency)

Install dev dependencies:

```bash
pip install -r requirements.txt
```

---

## Project structure

```
CardioDev-Guard/
├── core/
│   ├── models.py          # Shared data contracts (read this first)
│   ├── project_loader.py  # Discovers and categorises project files
│   ├── aggregator.py      # Merges and deduplicates analyzer findings
│   ├── explainer.py       # Enriches findings with human-readable explanations
│   ├── recommender.py     # Maps findings to actionable recommendations
│   └── orchestrator.py    # Drives the full pipeline end-to-end
├── tests/                 # Unit tests (one file per core module)
├── requirements.txt
└── README.md
```

The `core/` package is importable directly from the repository root — no
installation step is needed.

---

## Running the pipeline

```python
from core.orchestrator import run_pipeline

output = run_pipeline(
    project_path="./my_ml_project",
    analyzers=[],          # pass your analyzer callables here
)

print(output.overall_status)    # OverallStatus.READY / NEEDS_WORK / CRITICAL
print(output.summary)           # plain-English one-paragraph summary
print(output.findings)          # list of Finding objects, CRITICAL first
print(output.recommendations)   # list of Recommendation objects, priority 1 first
```

---

## How teammates register analyzers

Each analyzer is a plain Python function that accepts an `AnalysisRequest`
and returns an `AnalyzerResult`:

```python
from core.models import AnalysisRequest, AnalyzerResult, Finding, Severity

def my_analyzer(request: AnalysisRequest) -> AnalyzerResult:
    findings = []

    # Use the pre-categorised file lists on the request:
    #   request.model_files   — .pkl, .h5, .pt, .joblib, .onnx
    #   request.data_files    — .csv, .json, .parquet, .xlsx
    #   request.test_files    — test_*.py / *_test.py
    #   request.source_files  — other .py files
    #   request.doc_files     — .md, .txt, .rst

    if not request.data_files:
        findings.append(Finding(
            severity=Severity.HIGH,
            category="data_quality",
            title="No dataset files found",
            description="The project contains no recognisable dataset files.",
        ))

    return AnalyzerResult(
        analyzer_name="My Analyzer",
        findings=findings,
    )


# Register by passing the function to run_pipeline:
from core.orchestrator import run_pipeline

output = run_pipeline(
    project_path="./my_ml_project",
    analyzers=[my_analyzer],
)
```

If an analyzer raises an unhandled exception, the pipeline catches it, records
it as a `CRITICAL` finding, and continues running the remaining analyzers.

---

## Data model reference

All shared types live in [`core/models.py`](core/models.py).

| Type | Role |
|---|---|
| `ProjectInput` | Raw user-supplied path and project name |
| `AnalysisRequest` | Enriched input passed to every analyzer; contains categorised file lists |
| `Finding` | A single issue detected by an analyzer — has `severity`, `category`, `title`, `description` |
| `AnalyzerResult` | Return value from one analyzer callable — wraps a list of `Finding` objects |
| `Recommendation` | An actionable fix linked to a `Finding` by `finding_id` |
| `StructuredOutput` | Final pipeline result consumed by UI, report generator, and test runner |

**Severity levels** (high → low): `CRITICAL (5)` › `HIGH (4)` › `MEDIUM (3)` › `LOW (2)` › `INFO (1)`

**Overall status**:
- `READY` — no CRITICAL or HIGH findings
- `NEEDS_WORK` — at least one HIGH finding
- `CRITICAL` — at least one CRITICAL finding; do not release

**Agreed `Finding.category` strings** — teammate analyzers must use one of:

| Category | Produced by |
|---|---|
| `data_quality` | ML/data analyzer |
| `model_performance` | ML/data analyzer |
| `test_coverage` | Test analyzer |
| `documentation` | Test analyzer |
| `dependency` | Test analyzer |
| `code_quality` | Test analyzer |
| `analyzer_failure` | Orchestrator (auto-injected on crash) |

---

## Running tests

```bash
pytest tests/
```

Tests require `pytest>=7.0` (see `requirements.txt`).  
Each test file is independent and uses only the Python standard library — no
external services or real ML projects needed.
