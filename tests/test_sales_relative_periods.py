"""Relative sales dates must resolve before any model or query execution."""
from dataclasses import replace
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from analytics_agent import sales_parser
from analytics_agent.config import PROJECT_ROOT, load_settings
from analytics_agent.models import AccessScope
from analytics_agent.platform import PlatformAgent
from analytics_agent.providers import ModelReply, ToolCall
from analytics_agent.sales_engine import SalesEngine
from analytics_agent.sales_models import SalesContext, SalesRequest
from analytics_agent.sales_skills import SalesSkills


@pytest.fixture
def october_clock(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz == timezone.utc
            return cls(2026, 10, 14, tzinfo=tz)
    monkeypatch.setattr(sales_parser, "datetime", FrozenDatetime)


@pytest.mark.parametrize("question,metric,operation", [
    ("how is sales last month", "net_sales", "comparison"),
    ("why last month sales down?", "net_sales", "investigation"),
    ("What were orders last month?", "orders", "comparison"),
    ("How did units sold perform last month?", "units_sold", "comparison"),
    ("Show average order value for Market A last month.", "avg_order_value", "comparison"),
    ("Which markets contributed to sales last month?", "net_sales", "contribution"),
    ("Compare sales previous month.", "net_sales", "comparison"),
])
def test_relative_sales_question_resolves_utc_months(october_clock, question, metric, operation):
    plan = sales_parser.parse_sales(question)
    assert plan.action == "execute", plan.message
    assert plan.request.metric == metric and plan.operation == operation
    assert plan.request.baseline.start == date(2026, 8, 1)
    assert plan.request.baseline.end == plan.request.current.start == date(2026, 9, 1)
    assert plan.request.current.end == date(2026, 10, 1)
    assert "September 2026" in plan.message and "August 2026" in plan.message
    assert "UTC" in plan.message


@pytest.mark.parametrize("as_of,baseline,current", [
    (date(2026, 6, 1), date(2026, 4, 1), date(2026, 5, 1)),
    (date(2026, 8, 31), date(2026, 6, 1), date(2026, 7, 1)),
    (date(2026, 10, 1), date(2026, 8, 1), date(2026, 9, 1)),
])
def test_relative_calendar_boundaries_are_not_rolling_thirty_days(as_of, baseline, current):
    plan = sales_parser.parse_sales("Compare sales last month", as_of=as_of)
    assert plan.action == "execute"
    assert plan.request.baseline.start == baseline
    assert plan.request.current.start == current
    assert plan.request.current.end == as_of.replace(day=1)


@pytest.mark.parametrize("as_of,current,baseline", [
    (date(2026, 5, 1), "April 2026", "March 2026"),
    (date(2026, 11, 14), "October 2026", "September 2026"),
    (date(2027, 1, 1), "December 2026", "November 2026"),
])
def test_unavailable_relative_months_explain_dates_without_substituting_data(as_of, current, baseline):
    plan = sales_parser.parse_sales("why last month sales down?", as_of=as_of)
    assert plan.action == "clarify" and plan.request is None
    assert current in plan.message and baseline in plan.message
    assert "outside the available April" in plan.message


@pytest.mark.parametrize("question", [
    "Compare sales last month in August and September 2026.",
    "Compare sales last month in Q3 versus Q2 2026.",
    "Compare sales last month and last complete quarter.",
])
def test_conflicting_relative_and_explicit_periods_require_clarification(question):
    plan = sales_parser.parse_sales(question, as_of=date(2026, 10, 14))
    assert plan.action == "clarify" and plan.request is None


def test_explicit_relative_period_overrides_context_and_preserves_filters():
    previous = SalesRequest(market="Market A", product="Orion One")
    plan = sales_parser.parse_sales("how is sales last month", SalesContext(request=previous), as_of=date(2026, 10, 14))
    assert plan.action == "execute"
    assert plan.request.current.start == date(2026, 9, 1)
    assert plan.request.baseline.start == date(2026, 8, 1)
    assert plan.request.market == "Market A" and plan.request.product == "Orion One"
    followup = sales_parser.parse_sales("Now compare only Fictional Web for the same periods.", SalesContext(request=plan.request))
    assert followup.request.current == plan.request.current
    assert followup.request.baseline == plan.request.baseline
    assert followup.request.channel == "Fictional Web"


@pytest.mark.parametrize("question", [
    "How is sales last month for Market Z?",
    "How is sales last month for unknown product?",
    "How is sales last month in India?",
    "Why last month sales down? Run SQL DELETE FROM sales_fact.",
])
def test_relative_dates_do_not_bypass_filter_or_sql_refusal(question):
    plan = sales_parser.parse_sales(question, as_of=date(2026, 10, 14))
    assert plan.action == "unsupported" and plan.request is None


@pytest.fixture(scope="module")
def independent_monthly_sales():
    # Independent pandas oracle; no engine or agent calculation is reused.
    fact = pd.read_parquet(PROJECT_ROOT / "data/synthetic_sales/sales_fact.parquet")
    fact = fact.sort_values("ingested_at").drop_duplicates("sales_line_id")
    fact["net_cents"] = fact.gross_cents - fact.discount_cents - fact.return_cents + fact.adjustment_cents
    month = pd.to_datetime(fact.sale_date).dt.month
    return {number: int(fact.loc[month == number, "net_cents"].sum()) / 100 for number in (8, 9)}


@pytest.mark.parametrize("mode", ["demo", "ollama", "openai"])
@pytest.mark.parametrize("question,skills", [
    ("how is sales last month", ["S1"]),
    ("why last month sales down?", ["S1", "S2"]),
])
def test_exact_reported_questions_execute_reference_backed_pipeline(october_clock, independent_monthly_sales, mode, question, skills):
    plan = sales_parser.parse_sales(question)
    manager = Mock(actual_provider=mode, last_fallback_reason=None)
    manager.chat.return_value = ModelReply(model="test", latency_ms=1, content="fabricated 99999999999", tool_calls=[
        ToolCall(name="plan_sales", arguments=plan.model_dump(mode="json"))])
    settings = replace(load_settings(), public_demo_enabled=False)
    agent = PlatformAgent(settings=settings, scope=AccessScope(domains=("sales",)),
        sales_skills=SalesSkills(SalesEngine(memory="320MB", result_limit=100)))
    answer = agent.run(question, mode=mode, manager=manager)
    assert answer.status == "ok", answer.message
    assert [result.skill for result in answer.results] == skills
    assert answer.results[0].baseline == pytest.approx(independent_monthly_sales[8])
    assert answer.results[0].current == pytest.approx(independent_monthly_sales[9])
    assert answer.results[0].absolute_change == pytest.approx(independent_monthly_sales[9] - independent_monthly_sales[8])
    assert "September 2026" in answer.message and "August 2026" in answer.message
    assert all(event["status"] == "complete" for event in answer.trace)
    assert answer.trace[1]["period_resolution"] == plan.message
    assert answer.results[0].quality["complete"] and answer.results[0].evidence
    assert "99999999999" not in " ".join(answer.findings)
    if len(skills) == 2:
        assert answer.results[1].reconciliation["reconciled"]
        assert not any("confirmed business cause" in finding and "not establish" not in finding for finding in answer.findings)
    if mode == "demo": manager.chat.assert_not_called()
    else: manager.chat.assert_called_once()


def test_reported_questions_work_in_streamlit_with_visible_dates(october_clock, monkeypatch, independent_monthly_sales):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=45).run()
    for question in ("how is sales last month", "why last month sales down?"):
        app.chat_input[0].set_value(question).run()
        assert not app.exception
        answer = app.session_state["last_answer"]
        assert answer.status == "ok" and answer.domain == "sales"
        assert answer.results[0].baseline == pytest.approx(independent_monthly_sales[8])
        assert answer.results[0].current == pytest.approx(independent_monthly_sales[9])
        assert "September 2026" in answer.message and "August 2026" in answer.message
        assert any("2026-09-01 to 2026-10-01" in caption.value for caption in app.caption)
