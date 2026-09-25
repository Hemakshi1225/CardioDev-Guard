"""
Scanner — CardioDev-Guard
===========================
Workflow orchestrator. Collects AuditResults from all registered
adapter modules and assembles a ScanReport for the dashboard.

This module owns NO audit logic. It only:
  1. Calls each adapter's run() to retrieve whatever findings
     the respective team has injected.
  2. Packages the results into a ScanReport.
  3. Surfaces any adapter-level crashes as BLOCKER findings so the
     dashboard always has a complete, renderable report.

Integration map
---------------
  cardiodev_guard/auditors/ml_audit.py      <- ML team injects via inject_results()
  cardiodev_guard/auditors/qa_audit.py      <- QA team injects via inject_results()
  cardiodev_guard/auditors/release_audit.py <- Release team injects via inject_results()
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cardiodev_guard.findings import AuditDomain, AuditResult, Finding, Severity, ScanReport
from cardiodev_guard.auditors import ml_audit, qa_audit, release_audit

# Ordered list of (adapter_module, domain_enum) pairs.
# Add new team adapters here when the project grows.
_ADAPTERS = [
    (ml_audit,      AuditDomain.ML),
    (qa_audit,      AuditDomain.QA),
    (release_audit, AuditDomain.RELEASE),
]


def run_scan(project_path: str | Path) -> ScanReport:
    """
    Collect AuditResults from all adapters and return a ScanReport.

    Parameters
    ----------
    project_path : str or Path
        Project root passed through to each adapter's run() for
        interface consistency. Adapters may or may not use it.

    Returns
    -------
    ScanReport
        Aggregated results from all adapter modules.
    """
    project_path = Path(project_path).resolve()

    report = ScanReport(
        scan_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        project_path=str(project_path),
    )

    for adapter, domain in _ADAPTERS:
        try:
            result = adapter.run(project_path)
            report.audit_results.append(result)
        except Exception as exc:
            # An adapter crash must never bring down the whole scan.
            # Surface it as a BLOCKER finding in that domain.
            error_result = AuditResult(domain=domain)
            error_result.findings.append(Finding(
                id=f"{domain.value.lower()}.adapter_error",
                domain=domain,
                severity=Severity.BLOCKER,
                category="Adapter",
                title=f"{domain.value} adapter raised an unexpected error",
                evidence=str(exc),
                explanation=(
                    "The adapter module crashed before it could return findings. "
                    "This domain's results are incomplete."
                ),
                suggested_fix="Check the adapter module for import errors or missing dependencies.",
                validation_method="Scan completes without this error finding.",
            ))
            report.audit_results.append(error_result)

    return report
