"""
core/explainer.py — Issue explanation enrichment for CardioDev Guard
=====================================================================

Public API
----------
::

    from core.explainer import explain

    enriched = explain(findings)

Accepts a list of :class:`~core.models.Finding` objects (typically the
output of :func:`core.aggregator.aggregate`) and returns the same list
with each finding's ``description`` field replaced by a richer,
human-readable explanation — provided the finding's ``category`` has an
entry in :data:`EXPLANATION_RULES`.

Findings whose category is not in the rule table are returned **unchanged**,
so this module is safe to call even when teammate analyzers introduce new
categories that have not yet been documented here.

EXPLANATION_RULES
-----------------
An internal ``dict[str, str]`` mapping category strings to template strings.
Each template may reference ``{title}`` and ``{severity}`` via
:meth:`str.format`.  To add support for a new category, add one entry to
:data:`EXPLANATION_RULES` — no other code needs to change.

Mutation policy
---------------
The function mutates the ``description`` field of each matched finding
**in place** and returns the original list object.  Callers that need the
original descriptions should pass a deep copy.
"""

from __future__ import annotations

from core.models import Finding


# ---------------------------------------------------------------------------
# Explanation rule table
# ---------------------------------------------------------------------------

# Keys are the agreed Finding.category strings (see core/models.py).
# Values are template strings; use {title} and {severity} as placeholders.

_EXPLANATION_RULES: dict[str, str] = {
    "data_quality": (
        "[{severity}] Data Quality Issue: {title}\n\n"
        "Data quality problems directly undermine model reliability. "
        "Issues such as missing values, duplicate records, label noise, "
        "or out-of-distribution samples cause models to learn incorrect "
        "patterns and produce untrustworthy predictions. "
        "This must be resolved before training or evaluation to ensure "
        "results are meaningful and reproducible."
    ),
    "model_performance": (
        "[{severity}] Model Performance Issue: {title}\n\n"
        "Model performance issues indicate that the trained model does not "
        "meet the quality bar required for release. "
        "Poor accuracy, high error rates, underfitting, or overfitting mean "
        "the model will not perform reliably on real-world data. "
        "Review the training pipeline, feature engineering, and evaluation "
        "metrics before considering deployment."
    ),
    "test_coverage": (
        "[{severity}] Test Coverage Issue: {title}\n\n"
        "Insufficient test coverage leaves critical code paths unverified. "
        "Without adequate tests, regressions go undetected, making it "
        "unsafe to refactor or extend the codebase. "
        "Increase unit and integration test coverage, especially for data "
        "preprocessing, model inference, and evaluation logic."
    ),
    "documentation": (
        "[{severity}] Documentation Issue: {title}\n\n"
        "Missing or incomplete documentation reduces the project's "
        "maintainability and reproducibility. "
        "Reviewers, collaborators, and future contributors need clear "
        "explanations of the dataset, model architecture, training "
        "procedure, and evaluation results to assess and reproduce the work. "
        "Add or update README files, docstrings, and inline comments."
    ),
    "dependency": (
        "[{severity}] Dependency Issue: {title}\n\n"
        "Unmanaged or conflicting dependencies create reproducibility "
        "problems and security risks. "
        "If library versions are not pinned, the project may break when "
        "dependencies are updated and cannot be reliably reproduced in "
        "other environments. "
        "Ensure all dependencies are listed in requirements.txt (or "
        "equivalent) with pinned versions."
    ),
    "code_quality": (
        "[{severity}] Code Quality Issue: {title}\n\n"
        "Code quality problems make the project harder to understand, "
        "maintain, and debug. "
        "Issues such as overly complex functions, lack of type annotations, "
        "unused imports, or inconsistent style slow down development and "
        "increase the risk of introducing bugs. "
        "Refactor the affected code and enforce a consistent style guide."
    ),
    "analyzer_failure": (
        "[{severity}] Analyzer Failure: {title}\n\n"
        "One of the automated analyzers did not complete successfully. "
        "This means part of the project has not been fully inspected and "
        "the overall assessment may be incomplete. "
        "Review the error details, fix the underlying cause, and re-run "
        "the analysis to ensure a complete quality report."
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explain(findings: list[Finding]) -> list[Finding]:
    """Enrich each finding's description using the explanation rule table.

    For every :class:`~core.models.Finding` in *findings*:

    * If ``finding.category`` has an entry in :data:`_EXPLANATION_RULES`,
      the finding's ``description`` is replaced with the rendered template
      (``{title}`` and ``{severity}`` substituted from the finding itself).
    * If the category has no rule, the finding is left **unchanged**.

    The list is mutated in place and then returned, so the return value
    is always the same object as the argument.

    Parameters
    ----------
    findings:
        List of :class:`~core.models.Finding` objects, typically produced
        by :func:`core.aggregator.aggregate`.  May be empty.

    Returns
    -------
    list[Finding]
        The same list, with ``description`` fields enriched where a rule
        exists.  Returns an empty list unchanged when *findings* is empty.

    Examples
    --------
    ::

        from core.explainer import explain
        from core.models import Finding, Severity

        f = Finding(
            severity=Severity.HIGH,
            category="data_quality",
            title="Missing values in training set",
            description="raw analyzer output",
        )
        explain([f])
        print(f.description)  # enriched human-readable explanation
    """
    for finding in findings:
        template = _EXPLANATION_RULES.get(finding.category)
        if template is not None:
            finding.description = template.format(
                title=finding.title,
                severity=finding.severity.name,
            )
    return findings
