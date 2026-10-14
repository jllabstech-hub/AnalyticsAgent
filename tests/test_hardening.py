"""Audit regressions: hand-calculated outputs and trust-boundary failures."""
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import pandas as pd
import pytest
from analytics_agent.agent import AnalyticsAgent, ConversationContext, computed_findings, parse_demo
from analytics_agent.config import load_settings
from analytics_agent.engine import DEADLINE
from analytics_agent.models import AccessScope, AnalyticsRequest, Period
from analytics_agent.providers import ModelReply, ProviderError, ProviderManager, ToolCall
from analytics_agent.skills import SkillRegistry, ToolArguments
from test_edge_cases import small


def test_service_contribution_routes_to_services():
    plan = parse_demo("Which services contributed most to the decline?", ConversationContext(request=AnalyticsRequest()))
    assert plan.action == "execute" and plan.tasks[0].dimension == "service"


@pytest.mark.parametrize("question", [
    "Compare August and September active users for Service Delta.",
    "Compare August and September active users for Market Zeta.",
    "Compare August and September active users for device Pixel X.",
    "Compare August 1 and August 2 active users.",
    "Compare August and September active users and forecast October 2027.",
])
def test_unhandled_filters_or_dates_never_silently_run(question):
    plan = parse_demo(question)
    assert plan.action != "execute" and not plan.tasks


def test_new_versus_existing_means_active_user_cohorts():
    plan = parse_demo("Compare new versus existing users in August and September.")
    assert plan.request.metric == "mau" and plan.tasks[0].skill == "K3"


def test_trend_contains_zero_activity_calendar_days(small):
    request = AnalyticsRequest()
    trend, _ = small.trend(request, request.baseline)
    assert len(trend) == 31 and trend[1]["active_users"] == 0
    empty, _ = small.trend(AnalyticsRequest(market="Market B"), request.baseline)
    assert len(empty) == 31 and all(r["active_users"] == 0 for r in empty)


def test_adoption_device_population_includes_period_associations(small):
    request = AnalyticsRequest(metric="service_adoption_rate", device_model="Orion One")
    result = small.metric(request, request.current)[0][0]
    assert result.numerator == 1 and result.denominator == 1 and result.value == 1


def test_query_evidence_names_actual_executed_period(small):
    request = AnalyticsRequest()
    day = Period(start="2026-08-01",end="2026-08-02")
    _, evidence = small.metric(request,day,AccessScope(markets=("Market A",)))
    assert evidence.parameters["executed_period"] == day.model_dump(mode="json")
    assert evidence.parameters["authorized_scope"]["markets"] == ["Market A"]


def test_rate_delta_is_percentage_points(small):
    request = AnalyticsRequest(metric="activation_rate", baseline=Period(start="2026-08-01",end="2026-09-01"),current=Period(start="2026-09-01",end="2026-10-01"))
    result = SkillRegistry(small).execute("K1",ToolArguments(request=request))
    findings = computed_findings([result],"comparison")
    assert "-100.00 pp" in findings["change"]


def test_explanation_fallback_displays_actual_provider_and_model(small):
    ollama, cloud = Mock(), Mock()
    plan = parse_demo("Compare August and September active users.")
    cloud.chat.side_effect = [ModelReply(model="cloud-model",latency_ms=1,tool_calls=[ToolCall(name="plan_investigation",arguments=plan.model_dump(mode="json"))]), ProviderError("timeout","safe",True)]
    ollama.health.return_value = {"reachable":True,"model_available":True}
    ollama.chat.return_value = ModelReply(model="local-model",latency_ms=1,content='{"observation_ids":["limits"]}')
    answer = AnalyticsAgent(SkillRegistry(small)).run("Compare August and September active users.",mode="openai",manager=ProviderManager(ollama,cloud,"openai"))
    assert answer.status == "ok" and answer.provider == "ollama" and answer.model == "local-model"
    assert "Observed" in answer.message and answer.fallback_reason == "timeout"


def test_failed_provider_preserves_fallback_reason(small):
    ollama, cloud = Mock(), Mock()
    cloud.chat.side_effect = ProviderError("missing_key","safe",True)
    ollama.health.side_effect = ProviderError("connection","safe",True)
    answer = AnalyticsAgent(SkillRegistry(small)).run("Compare August and September active users.",mode="openai",manager=ProviderManager(ollama,cloud,"openai"))
    assert answer.status == "error" and not answer.results and answer.fallback_reason == "missing_key"


def test_followups_preserve_periods_and_authorized_markets(small):
    agent = AnalyticsAgent(SkillRegistry(small),scope=AccessScope(markets=("Market B",)))
    answer = agent.run("Compare July and August active users.",mode="demo")
    for followup in answer.followups:
        plan = parse_demo(followup,answer.context)
        assert plan.action == "execute"
        assert plan.request.baseline == answer.context.request.baseline
        assert plan.request.current == answer.context.request.current
        assert plan.request.market is None or plan.request.market == "Market B"


@pytest.mark.parametrize("value", ["nan","inf","-inf"])
def test_nonfinite_execution_budgets_are_rejected(monkeypatch,value):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS",value)
    with pytest.raises(ValueError): load_settings()


def test_incomplete_chart_dates_are_gaps_not_zero(small):
    path = small.data_dir / "data_quality_status.parquet"
    quality = pd.read_parquet(path)
    quality["available_through"] = pd.Timestamp("2026-09-24")
    quality["complete"] = False
    quality.to_parquet(path,index=False)
    trend,_ = small.trend(AnalyticsRequest(),AnalyticsRequest().current)
    assert trend[22]["active_users"] == 0 and all(r["active_users"] is None for r in trend[23:])
    result = SkillRegistry(small).execute("K1",ToolArguments(request=AnalyticsRequest()))
    assert result.quality["complete"] is False
    assert computed_findings([result],"comparison")["change"].startswith("Provisional comparison")


def test_conflicting_duplicate_payloads_withhold_results(small):
    path = small.data_dir / "service_activity.parquet"
    events = pd.read_parquet(path)
    events.loc[1,"service"] = "Service Beta"
    events.to_parquet(path,index=False)
    with pytest.raises(ValueError,match="Conflicting duplicate"):
        SkillRegistry(small).execute("K1",ToolArguments(request=AnalyticsRequest()))


def test_impossible_ingestion_timestamp_withholds_results(small):
    path = small.data_dir / "service_activity.parquet"
    events = pd.read_parquet(path)
    events.loc[0,"ingested_at"] = pd.Timestamp("2026-07-01")
    events.to_parquet(path,index=False)
    with pytest.raises(ValueError,match="temporal validity"):
        SkillRegistry(small).execute("K1",ToolArguments(request=AnalyticsRequest()))


def test_shared_engine_bounds_sessions_and_coalesces_duplicate_work(small,monkeypatch):
    original = small._metric
    calls = []
    barrier = threading.Barrier(4)
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(small,"_metric",counted)
    def execute(_):
        barrier.wait(timeout=3)
        return small.metric(AnalyticsRequest(),AnalyticsRequest().current)
    with ThreadPoolExecutor(max_workers=4) as pool: answers = list(pool.map(execute,range(4)))
    assert len(calls) == 1 and all(a[0][0].value == 1 for a in answers)
    assert sum(a[1].cache_hit for a in answers) == 3


def test_waiting_for_shared_warehouse_respects_deadline(small):
    def waiting():
        token = DEADLINE.set(time.perf_counter()+.02)
        try:
            with pytest.raises(TimeoutError): small.metric(AnalyticsRequest(),AnalyticsRequest().current)
        finally: DEADLINE.reset(token)
    with small.session():
        with ThreadPoolExecutor(max_workers=1) as pool: pool.submit(waiting).result(timeout=2)


def test_adoption_requires_membership_and_device_to_overlap_each_other(small):
    path = small.data_dir / "service_membership.parquet"
    members = pd.read_parquet(path)
    members.loc[0,"eligible_from"] = pd.Timestamp("2026-09-16")
    members.to_parquet(path,index=False)
    request = AnalyticsRequest(metric="service_adoption_rate",device_model="Orion One",service="Service Alpha")
    value = small.metric(request,request.current)[0][0]
    assert value.denominator == 0 and value.value is None


def test_metric_independent_validation_reuses_cache_with_correct_evidence(small):
    small.quality(AnalyticsRequest(metric="mau"))
    _,_,evidence = small.quality(AnalyticsRequest(metric="activation_rate"))
    assert all(item.cache_hit and item.parameters["metric"] == "activation_rate" for item in evidence)
