"""
Unified finding data structure for CardioDev-Guard.

Every auditor (ML, QA, Release) produces a list of Finding objects.
The dashboard and report layer consume only this structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    PASS = "PASS"


class AuditDomain(str, Enum):
    ML = "ML"
    QA = "QA"
    RELEASE = "RELEASE"


@dataclass
class Finding:
    """A single audit finding produced by any auditor module."""

    # Identity
    id: str                            # Unique slug, e.g. "ml.missing_model_file"
    domain: AuditDomain               # Which auditor raised this
    severity: Severity                 # BLOCKER | WARNING | PASS

    # Display
    title: str                         # Short one-line title shown in the dashboard
    evidence: str                      # Concrete evidence observed (file path, value, snippet)
    explanation: str                   # Why this matters
    suggested_fix: str                 # Actionable remediation step
    validation_method: str             # How to confirm the fix worked

    # Optional metadata
    category: str = ""                 # Logical grouping within a domain (e.g. "Data Quality")
    auto_fixable: bool = False         # Reserved for future auto-fix capability
    extra: dict = field(default_factory=dict)  # Arbitrary additional data for ML/QA modules


@dataclass
class AuditResult:
    """Aggregated output from one auditor domain."""

    domain: AuditDomain
    findings: list[Finding] = field(default_factory=list)

    # Allow auditors to attach rich metadata (e.g. model metrics dict)
    metadata: dict = field(default_factory=dict)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.BLOCKER]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def passes(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.PASS]

    @property
    def is_ready(self) -> bool:
        """Domain-level readiness: no blockers."""
        return len(self.blockers) == 0


@dataclass
class ScanReport:
    """Full scan report aggregating all domain results."""

    audit_results: list[AuditResult] = field(default_factory=list)
    scan_timestamp: str = ""
    project_path: str = ""

    @property
    def all_findings(self) -> list[Finding]:
        findings = []
        for r in self.audit_results:
            findings.extend(r.findings)
        return findings

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.all_findings if f.severity == Severity.BLOCKER]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.all_findings if f.severity == Severity.WARNING]

    @property
    def passes(self) -> list[Finding]:
        return [f for f in self.all_findings if f.severity == Severity.PASS]

    @property
    def release_ready(self) -> bool:
        """Overall project is release-ready only when no BLOCKER exists."""
        return len(self.blockers) == 0

    @property
    def release_status_label(self) -> str:
        if self.release_ready:
            return "READY FOR RELEASE"
        return "NOT READY — BLOCKERS PRESENT"
