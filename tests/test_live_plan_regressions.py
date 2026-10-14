"""Failures first observed with a real OpenAI plan; no live calls in regressions."""
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from analytics_agent.agent import AnalyticsAgent, Plan, Task, parse_demo
from analytics_agent.models import AccessScope, AnalyticsRequest, Period
from analytics_agent.providers import ModelReply, ToolCall


@pytest.mark.parametrize("provider", ["ollama", "openai"])
def test_recognized_month_comparison_preserves_approved_semantics(provider):
    question = "Compare August and September active users."
    request = AnalyticsRequest(
        baseline=Period(start="2026-08-01", end="2026-08-31"),
        current=Period(start="2026-09-01", end="2026-09-30"),
    )
    plan = Plan(action="execute", request=request,
        tasks=[Task(skill="K3"), Task(skill="K3")], intent="comparison")
    manager = Mock(actual_provider=provider, last_fallback_reason=None)
    manager.chat.side_effect = [
        ModelReply(model="test", latency_ms=1, tool_calls=[
            ToolCall(name="plan_investigation", arguments=plan.model_dump(mode="json"))]),
        ModelReply(model="test", latency_ms=1, content='{"observation_ids":["change"]}'),
    ]
    answer = AnalyticsAgent().run(question, mode=provider, manager=manager)
    assert answer.status == "ok"
    assert answer.context.request == AnalyticsRequest()
    assert [result.skill for result in answer.results] == ["K1"]
    assert (answer.results[0].baseline, answer.results[0].current) == (66025, 65292)
    assert answer.tool_calls == 1
    assert any(step["status"] == "approved question semantics applied" for step in answer.trace)


def test_duplicate_tasks_are_coalesced_by_effective_arguments():
    plan = Plan(action="execute", request=AnalyticsRequest(), tasks=[
        Task(skill="K1"), Task(skill="K1", dimension="service"),
        Task(skill="K2", dimension="market"), Task(skill="K2", dimension="service"),
        Task(skill="K3", cohort="registration"), Task(skill="K3", cohort="registration"),
    ])
    assert [(t.skill, t.dimension, t.cohort) for t in plan.tasks] == [
        ("K1", "market", "new_existing"), ("K2", "market", "new_existing"),
        ("K2", "service", "new_existing"), ("K3", "market", "registration")]


def test_semantic_correction_cannot_hide_unauthorized_model_filters():
    plan = parse_demo("Compare August and September active users.")
    plan = plan.model_copy(update={"request":AnalyticsRequest(market="Market B")})
    manager = Mock(actual_provider="openai",last_fallback_reason=None)
    manager.chat.return_value = ModelReply(model="test",latency_ms=1,tool_calls=[
        ToolCall(name="plan_investigation",arguments=plan.model_dump(mode="json"))])
    answer = AnalyticsAgent(scope=AccessScope(markets=("Market A",))).run(
        "Compare August and September active users.",mode="openai",manager=manager)
    assert answer.status == "error" and answer.tool_calls == 0
    assert "authorized scope" in answer.message


def test_day_level_llm_request_is_not_replaced_with_demo_months():
    request = AnalyticsRequest(metric="dau",
        baseline=Period(start="2026-08-01",end="2026-08-02"),
        current=Period(start="2026-08-02",end="2026-08-03"))
    plan = Plan(action="execute",request=request,tasks=[Task(skill="K1")])
    manager = Mock(actual_provider="openai",last_fallback_reason=None)
    manager.chat.side_effect = [
        ModelReply(model="test",latency_ms=1,tool_calls=[
            ToolCall(name="plan_investigation",arguments=plan.model_dump(mode="json"))]),
        ModelReply(model="test",latency_ms=1,content='{"observation_ids":["change"]}'),
    ]
    answer = AnalyticsAgent().run("Compare daily active users on August 1 and August 2, 2026.",
        mode="openai",manager=manager)
    assert answer.status == "ok" and answer.context.request == request
    assert [result.skill for result in answer.results] == ["K1"]


@pytest.mark.parametrize("question", [
    "Compare August and September active users.",
    "Compare new versus existing users in August and September.",
])
def test_repeated_result_charts_have_unique_streamlit_ids(question,monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30).run()
    app.toggle(key="demo_mode").set_value(True).run()
    app.chat_input[0].set_value(question).run()
    answer = app.session_state["last_answer"]
    assert answer.status == "ok"
    app.session_state["last_answer"] = answer.model_copy(update={"results":answer.results*2})
    app.run()
    assert not app.exception
    assert len(app.get("plotly_chart")) == 2
