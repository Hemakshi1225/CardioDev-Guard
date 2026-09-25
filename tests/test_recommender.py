"""
tests/test_recommender.py — Unit tests for core/recommender.py

Covers:
- Empty input returns []
- CRITICAL finding gets priority 1
- HIGH finding gets priority 2
- MEDIUM gets priority 3, LOW priority 4, INFO priority 5
- Recommendations sorted by priority ascending
- finding_id is linked correctly
- All seven required categories produce recommendations
- Category-level fallback (category, None) used when no exact severity match
- Generic fallback (None, None) used for unknown categories
- action_title and detail are non-empty for every finding
"""

import pytest

from core.recommender import recommend
from core.models import Finding, Recommendation, Severity


def _finding(severity: Severity, category: str = "data_quality",
             title: str = "Issue") -> Finding:
    return Finding(severity=severity, category=category,
                   title=title, description="d")


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_list_returns_empty(self):
        assert recommend([]) == []


# ---------------------------------------------------------------------------
# Priority mapping
# ---------------------------------------------------------------------------

class TestPriorityMapping:
    @pytest.mark.parametrize("severity,expected_priority", [
        (Severity.CRITICAL, 1),
        (Severity.HIGH,     2),
        (Severity.MEDIUM,   3),
        (Severity.LOW,      4),
        (Severity.INFO,     5),
    ])
    def test_priority_matches_severity(self, severity, expected_priority):
        f = _finding(severity)
        recs = recommend([f])
        assert len(recs) == 1
        assert recs[0].priority == expected_priority

    def test_critical_gets_priority_1(self):
        f = _finding(Severity.CRITICAL)
        recs = recommend([f])
        assert recs[0].priority == 1

    def test_high_gets_priority_2(self):
        f = _finding(Severity.HIGH)
        recs = recommend([f])
        assert recs[0].priority == 2


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

class TestSorting:
    def test_recommendations_sorted_ascending(self):
        findings = [
            _finding(Severity.INFO,     category="documentation",  title="A"),
            _finding(Severity.CRITICAL, category="data_quality",   title="B"),
            _finding(Severity.LOW,      category="code_quality",   title="C"),
            _finding(Severity.HIGH,     category="dependency",     title="D"),
            _finding(Severity.MEDIUM,   category="test_coverage",  title="E"),
        ]
        recs = recommend(findings)
        priorities = [r.priority for r in recs]
        assert priorities == sorted(priorities)

    def test_priority_1_comes_first(self):
        findings = [
            _finding(Severity.LOW),
            _finding(Severity.CRITICAL),
        ]
        recs = recommend(findings)
        assert recs[0].priority == 1


# ---------------------------------------------------------------------------
# finding_id linkage
# ---------------------------------------------------------------------------

class TestFindingIdLinkage:
    def test_finding_id_linked_correctly(self):
        f = _finding(Severity.HIGH)
        recs = recommend([f])
        assert recs[0].finding_id == f.finding_id

    def test_each_rec_linked_to_its_own_finding(self):
        f1 = _finding(Severity.CRITICAL, title="A")
        f2 = _finding(Severity.HIGH,     title="B")
        recs = recommend([f1, f2])
        finding_ids = {f1.finding_id, f2.finding_id}
        rec_ids = {r.finding_id for r in recs}
        assert rec_ids == finding_ids


# ---------------------------------------------------------------------------
# All required categories produce non-empty recommendations
# ---------------------------------------------------------------------------

class TestRequiredCategories:
    REQUIRED = [
        "data_quality",
        "model_performance",
        "test_coverage",
        "documentation",
        "dependency",
        "code_quality",
        "analyzer_failure",
    ]

    @pytest.mark.parametrize("category", REQUIRED)
    def test_category_produces_recommendation(self, category: str):
        f = _finding(Severity.CRITICAL, category=category)
        recs = recommend([f])
        assert len(recs) == 1
        assert recs[0].action_title != ""
        assert recs[0].detail       != ""

    @pytest.mark.parametrize("category", REQUIRED)
    def test_high_severity_produces_recommendation(self, category: str):
        f = _finding(Severity.HIGH, category=category)
        recs = recommend([f])
        assert len(recs) == 1
        assert recs[0].action_title != ""


# ---------------------------------------------------------------------------
# Fallback rules
# ---------------------------------------------------------------------------

class TestFallbackRules:
    def test_unknown_category_gets_generic_fallback(self):
        f = _finding(Severity.MEDIUM, category="completely_unknown_xyz")
        recs = recommend([f])
        assert len(recs) == 1
        assert recs[0].action_title != ""
        assert recs[0].detail       != ""

    def test_category_level_fallback_used_when_no_exact_severity_match(self):
        # analyzer_failure has no exact entry for MEDIUM; falls back to (analyzer_failure, None)
        f = _finding(Severity.MEDIUM, category="analyzer_failure")
        recs = recommend([f])
        assert len(recs) == 1
        assert recs[0].priority == 3  # MEDIUM

    def test_generic_fallback_for_every_severity(self):
        for sev in Severity:
            f = _finding(sev, category="no_such_category_ever")
            recs = recommend([f])
            assert len(recs) == 1

    def test_unknown_category_priority_still_correct(self):
        f = _finding(Severity.CRITICAL, category="unknown")
        recs = recommend([f])
        assert recs[0].priority == 1


# ---------------------------------------------------------------------------
# Output integrity
# ---------------------------------------------------------------------------

class TestOutputIntegrity:
    def test_one_recommendation_per_finding(self):
        findings = [_finding(s, title=f"T{i}")
                    for i, s in enumerate(Severity)]
        recs = recommend(findings)
        assert len(recs) == len(findings)

    def test_recommendation_fields_populated(self):
        f = _finding(Severity.HIGH, category="data_quality", title="Missing values")
        recs = recommend([f])
        assert isinstance(recs[0].finding_id, str)
        assert isinstance(recs[0].action_title, str)
        assert isinstance(recs[0].detail, str)
        assert isinstance(recs[0].priority, int)
