import pytest
from pydantic import ValidationError
from analytics_agent.models import AccessScope, AnalyticsRequest, Period
from analytics_agent.semantics import registry, resolve
from analytics_agent.skills import SkillRegistry, ToolArguments


def test_all_metrics_have_complete_versioned_definitions():
    assert len(registry()) == 6
    for definition in registry().values():
        assert definition.required_joins and definition.owner and definition.timezone == "UTC"
    with pytest.raises(ValueError):
        resolve("sales")


@pytest.mark.parametrize("skill", ["K1", "K2", "K3"])
def test_skills_have_computed_evidence(skill):
    result = SkillRegistry().execute(skill, ToolArguments(request=AnalyticsRequest()))
    assert result.absolute_change == result.current - result.baseline
    assert result.evidence and result.metric_version and result.skill_version
    assert result.quality["events"]["raw_rows"] > result.quality["events"]["unique_events"]
    if skill != "K1":
        assert result.reconciliation["reconciled"]
        assert sum(x["change"] for x in result.records) == pytest.approx(result.absolute_change)


def test_overlapping_service_distinct_counts_are_not_added():
    result = SkillRegistry().execute("K2", ToolArguments(request=AnalyticsRequest(), dimension="service"))
    assert not result.reconciliation["reconciled"]
    assert all(x["contribution_pct"] is None for x in result.records)


def test_incomplete_partition_is_flagged():
    result = SkillRegistry().execute("K1", ToolArguments(request=AnalyticsRequest(scenario="incomplete")))
    assert any("Incomplete reporting" in x for x in result.warnings)


def test_zero_denominator_is_undefined():
    period = Period(start="2026-07-01", end="2026-07-02")
    # A deliberately empty authorized population, independent of the fixture.
    request = AnalyticsRequest(metric="activation_rate", baseline=period, current=period)
    class EmptyEngine:
        def authorize(self, *args): pass
        def metric(self, *args):
            from analytics_agent.models import MetricValue, QueryEvidence
            return [MetricValue(value=None, numerator=0, denominator=0)], QueryEvidence(query_id="zero",template="test.empty",duration_ms=0,rows=1,parameters={},sources=["users"])
        def quality(self, *args): return [], {"raw_rows":0,"unique_events":0,"late_events":0}, []
        def trend(self, *args):
            from analytics_agent.models import QueryEvidence
            return [], QueryEvidence(query_id="empty",template="test.trend",duration_ms=0,rows=0,parameters={},sources=["users"])
    result = SkillRegistry(EmptyEngine()).execute("K1", ToolArguments(request=request))
    assert result.current is None and result.percentage_change is None
    assert any("Zero denominator" in x for x in result.warnings)


def test_unapproved_cohorts_and_skills_are_rejected():
    with pytest.raises(ValidationError):
        ToolArguments(request=AnalyticsRequest(), cohort="secret")
    with pytest.raises(PermissionError):
        SkillRegistry().execute("K2", ToolArguments(request=AnalyticsRequest()), AccessScope(skills=("K1",)))
