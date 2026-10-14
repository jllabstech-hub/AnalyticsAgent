"""Human questions traverse parser, agent, skills, SQL, validation and findings."""
import json
from pathlib import Path
import pytest
from analytics_agent.agent import AnalyticsAgent
from analytics_agent.engine import Engine
from analytics_agent.skills import SkillRegistry

CASES = json.loads((Path(__file__).parent / "fixtures" / "reference_answers.json").read_text())
NAMES = {"mau":"monthly active users","dau":"daily active users","new_users":"new users",
         "active_existing_users":"active existing users","activation_rate":"activation rate","service_adoption_rate":"service adoption rate"}


@pytest.fixture(scope="module")
def agent(): return AnalyticsAgent(SkillRegistry(Engine()))


@pytest.mark.parametrize("case",CASES,ids=lambda c:c["id"])
def test_natural_language_reference_e2e(agent,case):
    filters = " and ".join(case["filters"].values()) or "all users"
    question = f"Compare August and September {NAMES[case['metric']]} for {filters}."
    answer = agent.run(question,mode="demo")
    assert answer.status == "ok",answer.message
    assert [r.skill for r in answer.results] == ["K1"]
    result = answer.results[0]
    assert result.request.metric == case["metric"]
    assert result.baseline == pytest.approx(case["baseline"])
    assert result.current == pytest.approx(case["current"])
    assert result.quality["complete"] and result.evidence
    assert answer.provider == "deterministic demo" and answer.message.startswith("Observed")
    assert all(getattr(result.request,key) == value for key,value in case["filters"].items())
