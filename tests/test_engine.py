import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from pydantic import ValidationError
from analytics_agent.engine import Engine
from analytics_agent.models import AccessScope, AnalyticsRequest, Period

CASES = json.loads((Path(__file__).parent / "fixtures" / "reference_answers.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_independent_reference_comparisons(case):
    request = AnalyticsRequest(metric=case["metric"], **case["filters"])
    engine = Engine()
    for period, key in [(request.baseline, "baseline"), (request.current, "current")]:
        values, evidence = engine.metric(request, period)
        assert values[0].value == pytest.approx(case[key])
        assert evidence.rows >= 0 and evidence.duration_ms >= 0
        assert evidence.query_id and evidence.sources


def test_authorization_is_enforced_for_every_query():
    engine = Engine()
    scope = AccessScope(markets=("Market A",))
    with pytest.raises(PermissionError):
        engine.metric(AnalyticsRequest(market="Market B"), AnalyticsRequest().current, scope)
    values, _ = engine.metric(AnalyticsRequest(), AnalyticsRequest().current, scope)
    expected, _ = engine.metric(AnalyticsRequest(market="Market A"), AnalyticsRequest().current)
    assert values[0].value == expected[0].value


@pytest.mark.parametrize("args", [{"metric": "revenue"}, {"market": "x' OR 1=1"}, {"sql": "DELETE FROM users"}])
def test_unapproved_arguments_are_rejected(args):
    with pytest.raises(ValidationError):
        AnalyticsRequest(**args)


def test_invalid_dates_and_dimension():
    with pytest.raises(ValidationError):
        Period(start="2026-09-01", end="2026-09-01")
    with pytest.raises(ValueError):
        Engine().metric(AnalyticsRequest(), AnalyticsRequest().current, group_by="password")


def test_connections_are_isolated_between_threads():
    request = AnalyticsRequest(market="Market A")
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: Engine().metric(request, request.current)[0][0].value, range(2)))
    assert values[0] == values[1]
