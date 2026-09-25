"""
core/aggregator.py — Findings aggregation for CardioDev Guard
==============================================================

Public API
----------
::

    from core.aggregator import aggregate

    findings = aggregate(analyzer_results)

Takes a list of :class:`~core.models.AnalyzerResult` objects (one per
analyzer) and returns a single flat, deduplicated, severity-sorted list
of :class:`~core.models.Finding` objects.

Deduplication key
-----------------
Two findings are considered duplicates when they share the same
``(category, title, file_path)`` tuple.  When duplicates are detected
the copy with the **highest** :class:`~core.models.Severity` is kept and
the rest are discarded.

Synthetic failure findings
--------------------------
If an :class:`~core.models.AnalyzerResult` has ``success=False`` and a
non-empty ``error_message``, a synthetic ``CRITICAL`` finding is injected
with ``category="analyzer_failure"`` so the failure is visible in the
final output.  Any real findings already attached to a failed result are
still included.

Output order
------------
Findings are sorted by :class:`~core.models.Severity` descending:
``CRITICAL`` first, ``INFO`` last.
"""

from __future__ import annotations

from core.models import AnalyzerResult, Finding, Severity


def aggregate(results: list[AnalyzerResult]) -> list[Finding]:
    """Merge a list of analyzer results into one deduplicated, sorted list.

    Parameters
    ----------
    results:
        Zero or more :class:`~core.models.AnalyzerResult` objects returned
        by teammate analyzers.

    Returns
    -------
    list[Finding]
        Flat list of :class:`~core.models.Finding` objects, deduplicated by
        ``(category, title, file_path)`` and sorted from most to least
        severe (``CRITICAL`` → ``INFO``).  Returns an empty list when
        *results* is empty or all results contain no findings.
    """
    if not results:
        return []

    # Collect every finding, including synthetic ones for failed analyzers.
    # Use a dict keyed by (category, title, file_path) to deduplicate,
    # keeping the highest-severity copy encountered.
    seen: dict[tuple[str, str, str | None], Finding] = {}

    for result in results:
        # Inject a synthetic CRITICAL finding when an analyzer failed.
        if not result.success and result.error_message:
            _upsert(
                seen,
                Finding(
                    severity=Severity.CRITICAL,
                    category="analyzer_failure",
                    title=f"Analyzer failed: {result.analyzer_name}",
                    description=result.error_message,
                ),
            )

        for finding in result.findings:
            _upsert(seen, finding)

    # Sort by Severity descending (CRITICAL=5 → INFO=1).
    return sorted(seen.values(), key=lambda f: f.severity, reverse=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _upsert(
    seen: dict[tuple[str, str, str | None], Finding],
    finding: Finding,
) -> None:
    """Insert *finding* into *seen*, or replace the existing entry if the
    new finding has a higher severity."""
    key = (finding.category, finding.title, finding.file_path)
    existing = seen.get(key)
    if existing is None or finding.severity > existing.severity:
        seen[key] = finding
