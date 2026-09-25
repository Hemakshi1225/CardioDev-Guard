"""
QA Audit Adapter — CardioDev-Guard
=====================================
Integration point for the QA team's audit module.

THIS FILE CONTAINS NO AUDIT LOGIC.

The QA team implements the real checks in their own module and calls
inject_results() to push findings into this adapter before the
dashboard renders.

Dashboard-side contract (what this file owns):
  - run(project_path) -> AuditResult   called by scanner.py
  - inject_results(audit_result)        called by QA team's module

QA-team contract (what they must supply):
  - A list of Finding objects (see cardiodev_guard/findings.py)
  - Each Finding must have: id, domain=AuditDomain.QA, severity,
    title, evidence, explanation, suggested_fix, validation_method
"""

from __future__ import annotations

from pathlib import Path

from cardiodev_guard.findings import AuditDomain, AuditResult


# Module-level slot for results injected by the QA team's module.
_injected: AuditResult | None = None


def inject_results(audit_result: AuditResult) -> None:
    """
    Called by the QA team's module to push completed audit findings
    into this adapter before the dashboard scan runs.

    Parameters
    ----------
    audit_result : AuditResult
        A fully populated AuditResult with domain=AuditDomain.QA.
    """
    global _injected
    _injected = audit_result


def run(project_path: Path) -> AuditResult:  # noqa: ARG001
    """
    Return the QA audit result.

    If the QA team has injected results via inject_results(), those are
    returned as-is.  Otherwise returns an empty AuditResult so the
    dashboard renders the QA domain with a 'pending' state.
    """
    if _injected is not None:
        return _injected

    return AuditResult(domain=AuditDomain.QA)
