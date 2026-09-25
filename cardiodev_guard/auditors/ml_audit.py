"""
ML Audit Adapter — CardioDev-Guard
=====================================
Integration point for the ML team's (Tanish) core pipeline.

This adapter has two operating modes:

1. **Injected mode** (highest priority)
   If ``inject_results()`` has been called with a pre-built ``AuditResult``,
   ``run()`` returns it unchanged.  This allows unit tests and other callers
   to supply synthetic findings without touching the filesystem.

2. **Live core mode** (default)
   If nothing has been injected, ``run()`` delegates to
   ``cardiodev_guard.core_bridge.run_core_analysis()``, which internally
   calls ``core.orchestrator.run_pipeline()`` on the supplied project path
   and translates the ``StructuredOutput`` into a dashboard ``AuditResult``.

   Any core-contract analyzers registered via
   ``cardiodev_guard.core_bridge.register_analyzer()`` will be executed.
   If none are registered the core pipeline still runs (returning READY /
   no findings) so the dashboard is never left in an error state.

Errors during the live core run are caught here and surfaced as a single
BLOCKER finding so the dashboard always receives a renderable result.

Dashboard-side contract (what this file owns):
  - run(project_path) -> AuditResult   called by scanner.py
  - inject_results(audit_result)        called by tests / override callers

ML-team contract (what they must supply if they want to override live mode):
  - A list of Finding objects (see cardiodev_guard/findings.py)
  - Each Finding must have: id, domain=AuditDomain.ML, severity,
    title, evidence, explanation, suggested_fix, validation_method
"""

from __future__ import annotations

import sys
from pathlib import Path

from cardiodev_guard.findings import AuditDomain, AuditResult, Finding, Severity


# Module-level slot for results injected by override callers / tests.
_injected: AuditResult | None = None


def inject_results(audit_result: AuditResult) -> None:
    """
    Override the live core analysis by injecting a pre-built AuditResult.

    Once set, ``run()`` returns the injected result instead of calling
    the core bridge.  Call with ``None`` to reset to live mode.

    Parameters
    ----------
    audit_result : AuditResult or None
        A fully populated AuditResult with domain=AuditDomain.ML,
        or None to clear a previous injection.
    """
    global _injected
    _injected = audit_result


def run(project_path: Path) -> AuditResult:
    """
    Return the ML audit result for *project_path*.

    Priority order:
    1. Return the injected AuditResult if one was set via inject_results().
    2. Run the Tanish core pipeline via core_bridge.run_core_analysis()
       and return the translated AuditResult.
    3. On any error from the core pipeline, return an AuditResult
       containing a single BLOCKER finding describing the failure.

    Parameters
    ----------
    project_path : Path
        Project root passed to the core pipeline.
    """
    if _injected is not None:
        return _injected

    # Live mode: delegate to the core bridge.
    try:
        from cardiodev_guard.core_bridge import run_core_analysis
        return run_core_analysis(project_path)
    except Exception as exc:
        print(
            f"[CardioDev-Guard] WARNING: core bridge raised an error: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        error_result = AuditResult(domain=AuditDomain.ML)
        error_result.findings.append(
            Finding(
                id="ml.core_bridge_error",
                domain=AuditDomain.ML,
                severity=Severity.BLOCKER,
                category="analyzer_failure",
                title="Core analysis pipeline failed to run",
                evidence=f"{type(exc).__name__}: {exc}",
                explanation=(
                    "The Tanish core pipeline (core.orchestrator.run_pipeline) "
                    "raised an unexpected error. ML audit results are unavailable. "
                    "Check the project path and that all core dependencies are "
                    "installed."
                ),
                suggested_fix=(
                    "Review the error message above, verify the project path is "
                    "a valid directory, and re-run the scan."
                ),
                validation_method=(
                    "Scan completes without this BLOCKER finding in the ML domain."
                ),
            )
        )
        return error_result
