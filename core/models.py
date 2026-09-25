"""
core/models.py — Shared data contracts for CardioDev Guard
===========================================================

This is THE contract file for the entire project.

Every module in ``core/`` and every teammate's analyzer, UI module, and
report generator works with the types defined here.  Read this file to
understand what data flows between modules — nothing else is needed.

Data-flow summary
-----------------
::

    ProjectInput
        └─> AnalysisRequest   (produced by project_loader)
                └─> AnalyzerResult  (produced by each teammate analyzer)
                        └─> Finding (aggregated by aggregator)
                                └─> Recommendation (produced by recommender)
                                        └─> StructuredOutput (final result)

Serialization contract
----------------------
All fields use only standard Python types (str, int, float, bool, list,
dict, Optional).  To convert any dataclass to a plain dict call
``dataclasses.asdict(instance)``.  No third-party libraries are required
to import or use these models.

Agreed Finding categories
--------------------------
Teammate analyzers MUST set ``Finding.category`` to one of these strings:

* ``"data_quality"``      — produced by the ML/data analyzer
* ``"model_performance"`` — produced by the ML/data analyzer
* ``"test_coverage"``     — produced by the test analyzer
* ``"documentation"``     — produced by the test analyzer
* ``"dependency"``        — produced by the test analyzer
* ``"code_quality"``      — produced by the test analyzer
* ``"analyzer_failure"``  — injected automatically by the orchestrator

New categories can be added by updating this file and ``core/explainer.py``
together.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Severity(IntEnum):
    """Numeric severity levels for a :class:`Finding`.

    Higher integer value = more severe.  This ordering lets you sort
    findings from most to least critical with a plain ``sorted(..., reverse=True)``.

    Example::

        findings.sort(key=lambda f: f.severity, reverse=True)
    """

    INFO = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    CRITICAL = 5


class OverallStatus(Enum):
    """Release-readiness status for the whole project.

    Computed by the orchestrator from the aggregated findings:

    * ``READY``      — no HIGH or CRITICAL findings detected
    * ``NEEDS_WORK`` — at least one HIGH finding (but no CRITICAL)
    * ``CRITICAL``   — at least one CRITICAL finding; do not release
    """

    READY = "READY"
    NEEDS_WORK = "NEEDS_WORK"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

@dataclass
class ProjectInput:
    """Raw input provided by the user before any analysis begins.

    Attributes
    ----------
    path:
        Absolute or relative filesystem path to the root of the ML project
        being analysed.
    name:
        Human-readable project name used in reports and the UI.  Defaults
        to the last path component if not supplied.
    metadata:
        Optional free-form key/value pairs (e.g. ``{"version": "1.2.0"}``).
        The orchestrator passes this through unchanged; analyzers may read
        it but must not depend on specific keys being present.
    """

    path: str
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisRequest:
    """Enriched input that is passed to every teammate analyzer.

    Produced by ``core.project_loader.load_project()``.  Contains the
    original :class:`ProjectInput` plus categorised lists of file paths
    discovered inside the project directory.

    Analyzers should iterate the relevant list(s) for their domain
    (e.g. the ML analyzer reads ``model_files`` and ``data_files``).

    All path lists contain absolute path strings.

    Attributes
    ----------
    project_input:
        The original :class:`ProjectInput` that triggered this request.
    model_files:
        Paths to serialised model artefacts (.pkl, .h5, .pt, .joblib, .onnx).
    data_files:
        Paths to dataset files (.csv, .json, .parquet, .xlsx).
    test_files:
        Paths to test source files (files/dirs matching ``test_*`` or
        ``*_test.py`` patterns).
    source_files:
        All Python source files (.py) that are not test files.
    doc_files:
        Documentation files (.md, .txt, .rst).
    """

    project_input: ProjectInput
    model_files: list[str] = field(default_factory=list)
    data_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    doc_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Analyzer output models
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single issue or observation raised by an analyzer.

    Teammates create ``Finding`` instances inside their analyzer functions
    and return them inside an :class:`AnalyzerResult`.

    Attributes
    ----------
    severity:
        How serious this finding is.  Use :class:`Severity` constants.
    category:
        Which domain this finding belongs to.  Must be one of the agreed
        category strings documented in this module's docstring.
    title:
        Short, one-line description of the problem (≤ 80 characters).
    description:
        Detailed explanation of the issue, why it matters, and the impact.
        The explainer module may overwrite this with a richer template.
    finding_id:
        Unique identifier assigned automatically.  Do not set this manually.
    file_path:
        Path to the file where the issue was found, if applicable.
    line_number:
        Line number within ``file_path``, if applicable.
    raw_data:
        Any additional structured data the analyzer wants to attach
        (e.g. metrics, counts).  Must contain only JSON-serializable values.
    """

    severity: Severity
    category: str
    title: str
    description: str
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyzerResult:
    """The return value from a single analyzer callable.

    Each teammate's analyzer must return exactly one ``AnalyzerResult``.

    Attributes
    ----------
    analyzer_name:
        Human-readable name for this analyzer (e.g. ``"ML Data Analyzer"``).
        Used in reports and error messages.
    findings:
        All :class:`Finding` objects produced by this analyzer.  May be
        empty if the analyzer found no issues.
    success:
        ``True`` if the analyzer completed normally, ``False`` if it
        encountered an error that prevented full analysis.
    error_message:
        Human-readable description of the failure when ``success=False``.
        Ignored when ``success=True``.
    """

    analyzer_name: str
    findings: list[Finding] = field(default_factory=list)
    success: bool = True
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Recommendation model
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    """An actionable step linked to a specific :class:`Finding`.

    Produced by ``core.recommender.recommend()``.

    Attributes
    ----------
    finding_id:
        The ``finding_id`` of the :class:`Finding` this recommendation
        addresses.
    action_title:
        Short, imperative title (e.g. ``"Add null-value checks to dataset"``).
    detail:
        Full explanation of what to do and why, suitable for display in the
        UI or a report.
    priority:
        Lower number = more urgent.  Derived from finding severity:
        CRITICAL → 1, HIGH → 2, MEDIUM → 3, LOW → 4, INFO → 5.
    """

    finding_id: str
    action_title: str
    detail: str
    priority: int


# ---------------------------------------------------------------------------
# Final structured output
# ---------------------------------------------------------------------------

@dataclass
class StructuredOutput:
    """The complete, aggregated result of one pipeline run.

    Produced by ``core.orchestrator.run_pipeline()`` and consumed by the
    UI module, report generator, and test runner.

    Attributes
    ----------
    project_name:
        Name from :class:`ProjectInput`.
    timestamp:
        ISO 8601 datetime string of when the pipeline completed
        (e.g. ``"2024-06-01T14:32:00"``).
    analysis_request:
        The :class:`AnalysisRequest` used for this run (includes all
        discovered file paths).
    analyzer_results:
        One :class:`AnalyzerResult` per analyzer that was executed,
        including failed ones.
    findings:
        Flat, deduplicated, severity-sorted list of all :class:`Finding`
        objects from all analyzers.  CRITICAL findings appear first.
    recommendations:
        Priority-sorted list of :class:`Recommendation` objects covering
        the findings above.
    overall_status:
        Computed release-readiness status.  See :class:`OverallStatus`.
    summary:
        Plain-English paragraph suitable for a one-line dashboard display
        or email subject.
    """

    project_name: str
    timestamp: str
    analysis_request: AnalysisRequest
    analyzer_results: list[AnalyzerResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    overall_status: OverallStatus = OverallStatus.READY
    summary: str = ""
