"""
tests/test_explainer.py — Unit tests for core/explainer.py

Covers:
- Known categories have their description enriched
- All seven required categories are covered
- Unknown/future categories are left unchanged
- Empty input returns []
- {title} and {severity} are substituted in the rendered description
- Return value is the same list object (in-place mutation)
"""

import pytest

from core.explainer import explain
from core.models import Finding, Severity


def _finding(category: str, severity: Severity = Severity.HIGH,
             title: str = "Test title") -> Finding:
    return Finding(severity=severity, category=category,
                   title=title, description="original description")


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_list_returns_empty(self):
        result = explain([])
        assert result == []

    def test_returns_same_list_object_on_empty(self):
        lst: list = []
        assert explain(lst) is lst


# ---------------------------------------------------------------------------
# Known categories
# ---------------------------------------------------------------------------

class TestKnownCategories:
    KNOWN = [
        "data_quality",
        "model_performance",
        "test_coverage",
        "documentation",
        "dependency",
        "code_quality",
        "analyzer_failure",
    ]

    @pytest.mark.parametrize("category", KNOWN)
    def test_known_category_replaces_description(self, category: str):
        f = _finding(category, title="Specific issue for " + category)
        explain([f])
        assert f.description != "original description"

    @pytest.mark.parametrize("category", KNOWN)
    def test_title_substituted_in_description(self, category: str):
        title = "My unique title " + category
        f = _finding(category, title=title)
        explain([f])
        assert title in f.description

    @pytest.mark.parametrize("category", KNOWN)
    def test_severity_name_substituted_in_description(self, category: str):
        f = _finding(category, severity=Severity.CRITICAL)
        explain([f])
        assert "CRITICAL" in f.description

    def test_data_quality_description_mentions_data(self):
        f = _finding("data_quality")
        explain([f])
        assert "data" in f.description.lower()

    def test_model_performance_description_mentions_model(self):
        f = _finding("model_performance")
        explain([f])
        assert "model" in f.description.lower()

    def test_test_coverage_description_mentions_test(self):
        f = _finding("test_coverage")
        explain([f])
        assert "test" in f.description.lower()

    def test_documentation_description_mentions_documentation(self):
        f = _finding("documentation")
        explain([f])
        assert "doc" in f.description.lower()

    def test_dependency_description_mentions_depend(self):
        f = _finding("dependency")
        explain([f])
        assert "depend" in f.description.lower()

    def test_code_quality_description_mentions_code(self):
        f = _finding("code_quality")
        explain([f])
        assert "code" in f.description.lower()

    def test_analyzer_failure_description_mentions_analyzer(self):
        f = _finding("analyzer_failure")
        explain([f])
        assert "analyzer" in f.description.lower()


# ---------------------------------------------------------------------------
# Unknown / future categories
# ---------------------------------------------------------------------------

class TestUnknownCategories:
    def test_unknown_category_description_unchanged(self):
        f = _finding("some_future_category")
        explain([f])
        assert f.description == "original description"

    def test_unknown_category_other_fields_unchanged(self):
        f = _finding("future_cat", severity=Severity.LOW, title="Future issue")
        explain([f])
        assert f.severity == Severity.LOW
        assert f.title    == "Future issue"
        assert f.category == "future_cat"


# ---------------------------------------------------------------------------
# Mixed list
# ---------------------------------------------------------------------------

class TestMixedList:
    def test_known_and_unknown_in_same_call(self):
        known   = _finding("code_quality", title="Long function")
        unknown = _finding("xyz_category", title="Future thing")
        explain([known, unknown])
        assert known.description   != "original description"
        assert unknown.description == "original description"

    def test_multiple_known_categories_all_enriched(self):
        f1 = _finding("data_quality",     title="T1")
        f2 = _finding("model_performance", title="T2")
        f3 = _finding("test_coverage",    title="T3")
        explain([f1, f2, f3])
        for f in (f1, f2, f3):
            assert f.description != "original description"


# ---------------------------------------------------------------------------
# In-place mutation / return value
# ---------------------------------------------------------------------------

class TestReturnValue:
    def test_returns_same_list_object(self):
        f = _finding("data_quality")
        lst = [f]
        returned = explain(lst)
        assert returned is lst

    def test_returned_finding_is_same_object(self):
        f = _finding("data_quality")
        returned = explain([f])
        assert returned[0] is f
