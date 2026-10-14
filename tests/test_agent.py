from dataclasses import replace
from unittest.mock import Mock
import pytest
from analytics_agent.agent import AnalyticsAgent, ConversationContext, Plan, parse_demo
from analytics_agent.config import load_settings
from analytics_agent.models import AccessScope, AnalyticsRequest
from analytics_agent.providers import ModelReply, ToolCall


@pytest.mark.parametrize("question,skills", [("Compare August and September active users.",["K1"]), ("Investigate the September decline across markets and cohorts.",["K1","K2","K3"]), ("Can we trust the September activity data?",["K1"])])
def test_documented_routing(question, skills):
    assert [t.skill for t in parse_demo(question).tasks] == skills


@pytest.mark.parametrize("question", ["Show weather", "Compare emails for September"])
def test_unknown_followup_cannot_inherit_a_metric(question):
    context = ConversationContext(request=AnalyticsRequest())
    plan = parse_demo(question,context)
    assert plan.action == "unsupported" and not plan.tasks


def test_clarification_and_unsupported_requests_do_not_execute():
    agent = AnalyticsAgent()
    assert agent.run("Compare active users",mode="demo").status == "clarification"
    assert agent.run("Compare September revenue",mode="demo").status == "unsupported"
    assert agent.run("Compare October active users",mode="demo").status == "unsupported"


def test_comparison_and_authorized_followup_context():
    agent = AnalyticsAgent()
    first = agent.run("Compare August and September active users.",mode="demo")
    assert first.status == "ok" and first.results[0].baseline == 66025
    second = agent.run("Now compare only Market A for the same periods.", first.context,mode="demo")
    assert second.status == "ok" and second.context.request.market == "Market A"
    assert second.context.request.baseline == first.context.request.baseline


def test_multistep_investigation_executes_all_three_skills():
    answer = AnalyticsAgent().run("Investigate the September decline across markets and cohorts.",mode="demo")
    assert answer.status == "ok" and [r.skill for r in answer.results] == ["K1","K2","K3"]
    assert answer.tool_calls == 3 and answer.followups
    assert any("not a confirmed cause" in s for s in answer.findings)


def test_invalid_model_tool_call_and_unauthorized_context_are_blocked():
    manager = Mock(actual_provider="ollama",last_fallback_reason=None)
    manager.chat.return_value = ModelReply(model="test",latency_ms=1,content="999999 users",tool_calls=[ToolCall(name="execute_sql",arguments={"sql":"DELETE FROM users"})])
    assert AnalyticsAgent().run("Investigate September", mode="ollama", manager=manager).status == "error"
    restricted = AnalyticsAgent(scope=AccessScope(markets=("Market A",)))
    context = ConversationContext(request=AnalyticsRequest(market="Market B"))
    assert restricted.run("Now compare same periods", context,mode="demo").status == "error"


def test_execution_depth_is_bounded():
    settings = replace(load_settings(), investigation_depth=1)
    assert AnalyticsAgent(settings=settings).run("Investigate September decline",mode="demo").status == "error"


def test_model_plan_uses_computed_values_and_ignores_fabricated_content():
    manager = Mock(actual_provider="ollama",last_fallback_reason=None)
    plan = parse_demo("Compare August and September active users.")
    manager.chat.side_effect = [ModelReply(model="test",latency_ms=1,content="999999999 users",tool_calls=[ToolCall(name="plan_investigation",arguments=plan.model_dump(mode="json"))]), ModelReply(model="test",latency_ms=1,content='{"observation_ids":["change"]}')]
    answer = AnalyticsAgent().run("Compare August and September active users.",mode="ollama",manager=manager)
    assert answer.status == "ok" and answer.results[0].current == 65292
    assert "999999999" not in " ".join(answer.findings)
