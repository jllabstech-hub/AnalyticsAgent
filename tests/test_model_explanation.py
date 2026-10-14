from unittest.mock import Mock
from analytics_agent.agent import AnalyticsAgent, parse_demo
from analytics_agent.providers import ModelReply, ToolCall


def test_invalid_model_explanation_preserves_verified_computations():
    manager = Mock(actual_provider="ollama",last_fallback_reason=None)
    plan = parse_demo("Compare August and September active users.")
    manager.chat.side_effect = [ModelReply(model="test",latency_ms=1,tool_calls=[ToolCall(name="plan_investigation",arguments=plan.model_dump(mode="json"))]), ModelReply(model="test",latency_ms=1,content='["fabricated observation"]')]
    answer = AnalyticsAgent().run("Compare August and September active users.",mode="ollama",manager=manager)
    assert answer.status == "ok"
    assert answer.results[0].absolute_change == answer.results[0].current-answer.results[0].baseline
    assert "fabricated observation" not in " ".join(answer.findings)
