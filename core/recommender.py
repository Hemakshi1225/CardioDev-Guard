"""
core/recommender.py — Actionable recommendations for CardioDev Guard
=====================================================================

Public API
----------
::

    from core.recommender import recommend

    recommendations = recommend(findings)

Accepts a list of :class:`~core.models.Finding` objects (typically the
output of :func:`core.explainer.explain`) and returns a priority-sorted
list of :class:`~core.models.Recommendation` objects — one per finding.

Rule lookup order
-----------------
For each finding, the rule table is consulted in this order:

1. Exact match on ``(category, severity)``
2. Category-level fallback on ``(category, None)``
3. Global generic fallback ``(None, None)``

This guarantees every finding — including those from unknown future
categories — always receives at least one recommendation.

Priority mapping
----------------
Priority is derived directly from :class:`~core.models.Severity`:

==========  ========
Severity    Priority
==========  ========
CRITICAL    1
HIGH        2
MEDIUM      3
LOW         4
INFO        5
==========  ========

Lower priority number = more urgent.  The returned list is sorted
ascending by priority so the most urgent items come first.

Mutation policy
---------------
This function does **not** mutate its input findings.  A new
:class:`~core.models.Recommendation` is created for each finding and
collected into a fresh list.
"""

from __future__ import annotations

from core.models import Finding, Recommendation, Severity


# ---------------------------------------------------------------------------
# Priority mapping
# ---------------------------------------------------------------------------

_SEVERITY_TO_PRIORITY: dict[Severity, int] = {
    Severity.CRITICAL: 1,
    Severity.HIGH:     2,
    Severity.MEDIUM:   3,
    Severity.LOW:      4,
    Severity.INFO:     5,
}


# ---------------------------------------------------------------------------
# Recommendation rule table
# ---------------------------------------------------------------------------
# Keys: (category: str | None, severity: Severity | None)
#   - (category, severity) — exact match
#   - (category, None)     — category-level fallback for any severity
#   - (None, None)         — global generic fallback
#
# Values: (action_title: str, detail: str)

_RECOMMENDATION_RULES: dict[tuple[str | None, Severity | None], tuple[str, str]] = {

    # data_quality ──────────────────────────────────────────────────────────
    ("data_quality", Severity.CRITICAL): (
        "Halt training — fix critical data quality issue immediately",
        "A critical data quality issue was detected. Stop all training runs. "
        "Audit the dataset for missing values, label corruption, or severe "
        "class imbalance. Do not proceed to evaluation or deployment until "
        "the dataset has been cleaned and re-validated.",
    ),
    ("data_quality", Severity.HIGH): (
        "Resolve data quality issue before next training run",
        "A high-severity data quality problem will distort model learning. "
        "Identify and address the root cause (e.g. impute or drop missing "
        "values, remove duplicates, fix incorrect labels). Re-run data "
        "validation checks after the fix.",
    ),
    ("data_quality", None): (
        "Review and clean the affected dataset",
        "A data quality issue was flagged. Inspect the dataset for "
        "inconsistencies, missing entries, or outliers and apply appropriate "
        "cleaning steps. Document the changes made.",
    ),

    # model_performance ─────────────────────────────────────────────────────
    ("model_performance", Severity.CRITICAL): (
        "Do not release — model performance is below the minimum threshold",
        "Model performance is critically low. The model must not be deployed. "
        "Re-examine the training pipeline, feature set, and hyperparameters. "
        "Consider collecting more labelled data or switching model architecture.",
    ),
    ("model_performance", Severity.HIGH): (
        "Improve model performance before release",
        "Model performance is below the acceptable bar for release. "
        "Run additional experiments: tune hyperparameters, add regularisation, "
        "or improve feature engineering. Establish a clear minimum performance "
        "threshold and only release once it is met.",
    ),
    ("model_performance", None): (
        "Investigate and improve model metrics",
        "A model performance issue was detected. Review evaluation metrics, "
        "check for data leakage, and validate results on a held-out test set.",
    ),

    # test_coverage ─────────────────────────────────────────────────────────
    ("test_coverage", Severity.CRITICAL): (
        "Add tests immediately — critical code paths are untested",
        "Core functionality has no test coverage. Write unit and integration "
        "tests for data preprocessing, model inference, and evaluation logic "
        "before merging or releasing any code.",
    ),
    ("test_coverage", Severity.HIGH): (
        "Increase test coverage for high-risk modules",
        "Important modules lack sufficient test coverage. Add tests for the "
        "affected areas, ensure the test suite runs in CI, and aim for "
        "meaningful coverage of branching logic and edge cases.",
    ),
    ("test_coverage", None): (
        "Expand the test suite",
        "Test coverage is insufficient in some areas. Add targeted tests for "
        "the flagged files or functions and integrate them into the CI pipeline.",
    ),

    # documentation ─────────────────────────────────────────────────────────
    ("documentation", Severity.CRITICAL): (
        "Add missing critical documentation before release",
        "Essential documentation is absent. Add a README that covers: "
        "project purpose, dataset description, model architecture, training "
        "instructions, and evaluation results. Without this, the project "
        "cannot be reproduced or reviewed.",
    ),
    ("documentation", None): (
        "Improve project documentation",
        "Documentation is incomplete or missing. Update the README, add "
        "docstrings to public functions, and document any non-obvious "
        "design decisions.",
    ),

    # dependency ────────────────────────────────────────────────────────────
    ("dependency", Severity.CRITICAL): (
        "Pin all dependencies immediately",
        "Dependencies are unmanaged or contain known-vulnerable versions. "
        "Create or update requirements.txt with pinned version numbers for "
        "every library. Run a security audit (e.g. `pip-audit`) and upgrade "
        "any packages with known CVEs.",
    ),
    ("dependency", None): (
        "Manage and pin project dependencies",
        "Dependency management needs attention. Ensure all libraries are "
        "listed in requirements.txt with pinned versions so the project is "
        "reproducible across environments.",
    ),

    # code_quality ──────────────────────────────────────────────────────────
    ("code_quality", Severity.HIGH): (
        "Refactor high-complexity code before release",
        "High-complexity code increases the risk of bugs and makes the "
        "project hard to maintain. Break large functions into smaller ones, "
        "add type annotations, and remove unused imports. Consider running "
        "a linter (flake8, pylint) as part of CI.",
    ),
    ("code_quality", None): (
        "Address code quality issues",
        "Code quality problems were detected. Apply consistent style, "
        "reduce function complexity, and remove dead code. Running an "
        "automated linter can identify and track these issues systematically.",
    ),

    # analyzer_failure ──────────────────────────────────────────────────────
    ("analyzer_failure", Severity.CRITICAL): (
        "Fix the failing analyzer and re-run the full analysis",
        "An analyzer crashed during the pipeline run, leaving part of the "
        "project uninspected. Examine the error message, fix the underlying "
        "cause (missing file, bad format, dependency issue), and re-run the "
        "full analysis to obtain a complete quality report.",
    ),
    ("analyzer_failure", None): (
        "Investigate and re-run the failed analyzer",
        "An analyzer did not complete. Review the error details and re-run "
        "once the issue is resolved to ensure full project coverage.",
    ),

    # Generic fallback ──────────────────────────────────────────────────────
    (None, None): (
        "Review and address the flagged issue",
        "An issue was detected that does not yet have a specific remediation "
        "rule. Examine the finding details, assess the impact, and apply an "
        "appropriate fix before releasing the project.",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def recommend(findings: list[Finding]) -> list[Recommendation]:
    """Produce a priority-sorted list of recommendations for *findings*.

    For each :class:`~core.models.Finding`, one :class:`~core.models.Recommendation`
    is created by consulting :data:`_RECOMMENDATION_RULES` in this order:

    1. ``(finding.category, finding.severity)`` — exact match
    2. ``(finding.category, None)``             — category fallback
    3. ``(None, None)``                         — global generic fallback

    Parameters
    ----------
    findings:
        List of :class:`~core.models.Finding` objects to generate
        recommendations for.  May be empty.

    Returns
    -------
    list[Recommendation]
        One :class:`~core.models.Recommendation` per finding, sorted by
        ``priority`` ascending (1 = most urgent).  Returns an empty list
        when *findings* is empty.

    Examples
    --------
    ::

        from core.recommender import recommend
        from core.models import Finding, Severity

        f = Finding(
            severity=Severity.CRITICAL,
            category="data_quality",
            title="Missing values in training set",
            description="...",
        )
        recs = recommend([f])
        print(recs[0].priority)       # 1
        print(recs[0].action_title)   # "Halt training — fix critical data quality issue immediately"
    """
    if not findings:
        return []

    recommendations: list[Recommendation] = []

    for finding in findings:
        action_title, detail = _lookup(finding.category, finding.severity)
        recommendations.append(
            Recommendation(
                finding_id=finding.finding_id,
                action_title=action_title,
                detail=detail,
                priority=_SEVERITY_TO_PRIORITY[finding.severity],
            )
        )

    recommendations.sort(key=lambda r: r.priority)
    return recommendations


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lookup(category: str, severity: Severity) -> tuple[str, str]:
    """Return ``(action_title, detail)`` for the given category and severity.

    Tries in order:
    1. exact ``(category, severity)``
    2. ``(category, None)``
    3. ``(None, None)``  — always present, so this never raises
    """
    return (
        _RECOMMENDATION_RULES.get((category, severity))
        or _RECOMMENDATION_RULES.get((category, None))
        or _RECOMMENDATION_RULES[(None, None)]
    )
