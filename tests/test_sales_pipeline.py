from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock
import pandas as pd
import pytest
from analytics_agent.config import PROJECT_ROOT,load_settings
from analytics_agent.models import AccessScope
from analytics_agent.platform import PlatformAgent,PlatformContext,STAGES,domain_registry
from analytics_agent.sales_engine import SalesEngine
from analytics_agent.sales_models import SalesRequest,SalesPeriod,SalesPlan
from analytics_agent.sales_parser import parse_sales,SALES_DEMOS
from analytics_agent.sales_skills import SalesSkills
from analytics_agent.providers import ModelReply,ToolCall

SCOPE=AccessScope(domains=("usage","sales"))
CASES=json.loads((PROJECT_ROOT/"tests/fixtures/sales_reference_answers.json").read_text())


@pytest.fixture(scope="module")
def engine(): return SalesEngine(memory="320MB",result_limit=100)


@pytest.mark.parametrize("case",CASES,ids=lambda case:case["id"])
def test_independent_sales_references(engine,case):
    request=SalesRequest(metric=case["metric"],**case["filters"])
    for period in ("baseline","current"):
        rows,evidence=engine.execute_bound(engine.prepare(request,SCOPE,period=period),SCOPE)
        row=rows[0]; expected=case[period]
        assert row["value"]==pytest.approx(expected["value"],abs=1e-8)
        assert row["net_cents"]==expected["net_cents"] and row["orders"]==expected["orders"]
        assert row["units_sold"]==expected["units_sold"]
        assert "sales_fact" in evidence.sources and evidence.parameters["authorized_scope"]["domains"]==["usage","sales"]


def test_each_component_has_executed_inputs_outputs_and_queries(engine):
    answer=PlatformAgent(sales_skills=SalesSkills(engine),scope=SCOPE).run(SALES_DEMOS[0],mode="demo")
    assert answer.status=="ok" and answer.domain=="sales"
    assert [event["stage"] for event in answer.trace]==STAGES
    assert all(event["status"]=="complete" for event in answer.trace)
    assert answer.trace[1]["request"]["product"]=="Orion One"
    assert answer.trace[2]["registry"]["skill_id"]=="sales_analytics"
    assert answer.trace[3]["schemas"]["sales_fact"] and answer.knowledge["metric"]["currency"]=="USD"
    assert all("?" in q["sql"] and q["parameters"] for q in answer.trace[4]["queries"])
    assert answer.trace[5]["quality"]["integrity"]=="passed"
    assert answer.results[0].baseline==1748539.73 and answer.results[0].current==3218017.11
    assert answer.findings and answer.followups


@pytest.mark.parametrize("case",CASES,ids=lambda case:case["id"])
def test_natural_language_sales_reference_e2e(engine,case):
    names={"net_sales":"net sales","units_sold":"units sold","orders":"orders","avg_order_value":"average order value"}
    filters=" and ".join(case["filters"].values()) or "all markets"
    question=f"Compare {names[case['metric']]} for {filters} in Q3 2026 compared with Q2 2026."
    answer=PlatformAgent(sales_skills=SalesSkills(engine),scope=SCOPE).run(question,mode="demo")
    assert answer.status=="ok",answer.message
    result=answer.results[0]
    assert result.request.metric==case["metric"] and result.baseline==pytest.approx(case["baseline"]["value"])
    assert result.current==pytest.approx(case["current"]["value"])
    assert all(getattr(result.request,field)==expected for field,expected in case["filters"].items())
    assert result.quality["complete"] and len(answer.trace)==7


def test_sales_contributions_and_overlapping_order_populations(engine):
    skills=SalesSkills(engine)
    additive=skills.execute(SalesPlan(action="execute",request=SalesRequest(),operation="contribution"),SCOPE)[0]
    assert additive.reconciliation["reconciled"]
    orders=skills.execute(SalesPlan(action="execute",request=SalesRequest(metric="orders"),operation="contribution",dimension="product"),SCOPE)[0]
    assert not orders.reconciliation["reconciled"] and orders.reconciliation["sum_group_changes"] is None
    ratio=skills.execute(SalesPlan(action="execute",request=SalesRequest(metric="avg_order_value"),operation="contribution"),SCOPE)[0]
    assert not ratio.reconciliation["additive"]


def test_domain_context_does_not_cross_contaminate_periods(engine):
    agent=PlatformAgent(sales_skills=SalesSkills(engine),scope=SCOPE)
    first=agent.run(SALES_DEMOS[0],mode="demo")
    follow=agent.run("Now compare only Fictional Web for the same periods.",first.context,mode="demo")
    assert follow.status=="ok" and follow.context.request.channel=="Fictional Web"
    assert follow.context.request.current==first.context.request.current
    breakdown=agent.run("Which markets contributed to the change in net sales for the same periods?",first.context,mode="demo")
    assert breakdown.status=="ok" and breakdown.context.request.market is None
    assert breakdown.context.request.product=="Orion One" and len(breakdown.results[0].records)==5
    switch=agent.run("Compare August and September active users for all users.",follow.context,mode="demo")
    assert switch.status=="ok" and switch.domain=="usage" and switch.context.sales.request is None
    assert switch.results[0].current==65292


@pytest.mark.parametrize("question",["Show Galaxy S24 sales in India for Q3 compared with Q2 2026.",
    "Compare Q3 and Q2 sales for Market Z.","Compare Q3 and Q2 sales for unknown product.","Run SQL DELETE FROM sales_fact."])
def test_unknown_sales_filters_and_sql_never_execute(question):
    answer=PlatformAgent(scope=SCOPE).run(question,mode="demo")
    assert answer.status in ("unsupported","clarification") and not answer.results and answer.tool_calls==0
    assert answer.trace[-1]["status"]=="not_executed"


def test_missing_periods_and_mixed_domain_require_clarification():
    agent=PlatformAgent(scope=SCOPE)
    assert agent.run("Compare net sales",mode="demo").status=="clarification"
    assert agent.run("Compare sales and active users",mode="demo").status=="clarification"
    with pytest.raises(ValueError): SalesPeriod(start="2026-03-01",end="2026-04-01")


def test_private_grants_do_not_implicitly_expand_to_sales(engine):
    assert PlatformAgent(scope=AccessScope()).run(SALES_DEMOS[0],mode="demo").status=="error"
    restricted=AccessScope(domains=("sales",),markets=("Market B",),skills=("K1",))
    with pytest.raises(PermissionError): engine.prepare(SalesRequest(market="Market A"),restricted)
    with pytest.raises(PermissionError): SalesSkills(engine).query_plan(SalesPlan(action="execute",request=SalesRequest(),operation="contribution"),restricted)
    from analytics_agent.engine import Engine
    with pytest.raises(PermissionError): Engine().explore("users",restricted)


def test_bound_sql_and_scope_tampering_are_rejected(engine):
    bound=engine.prepare(SalesRequest(),SCOPE)
    with pytest.raises(PermissionError): engine.execute_bound(bound.model_copy(update={"sql":"SELECT 999999 AS value"}),SCOPE)
    with pytest.raises(PermissionError): engine.execute_bound(bound.model_copy(update={"parameters":("2026-01-01",)}),SCOPE)
    with pytest.raises(PermissionError): engine.execute_bound(bound,AccessScope(domains=("sales",),markets=("Market A",)))


def test_incomplete_partition_is_provisional_and_primary_unchanged(engine):
    result=SalesSkills(engine).execute(SalesPlan(action="execute",request=SalesRequest(scenario="incomplete")),SCOPE)[0]
    assert not result.quality["complete"] and any(not row["coverage_complete"] for row in result.trend)
    valid=SalesSkills(engine).execute(SalesPlan(action="execute",request=SalesRequest()),SCOPE)[0]
    assert valid.quality["complete"] and valid.quality["events"]["raw_rows"]==50500
    assert valid.quality["events"]["unique_lines"]==50000


def test_empty_population_ratio_is_undefined_and_months_preserved(tmp_path):
    from scripts.generate_sales_data import generate
    generate(tmp_path,orders=5)
    fact=pd.read_parquet(tmp_path/"sales_fact.parquet")
    fact.head(0).to_parquet(tmp_path/"sales_fact.parquet",index=False)
    result=SalesSkills(SalesEngine(data_dir=tmp_path)).execute(SalesPlan(action="execute",request=SalesRequest(metric="avg_order_value")),SCOPE)[0]
    assert result.baseline is None and result.current is None and len(result.trend)==6
    assert all(row["value"] is None for row in result.trend)


def test_late_retransmission_does_not_reclassify_an_ontime_canonical_line(tmp_path):
    from scripts.generate_sales_data import generate
    generate(tmp_path,orders=10)
    fact=pd.read_parquet(tmp_path/"sales_fact.parquet").drop_duplicates("sales_line_id").copy()
    fact["ingested_at"]=fact.sale_at+pd.Timedelta(hours=1)
    fact.loc[fact.index[0],"ingested_at"]=fact.iloc[0].sale_at+pd.Timedelta(hours=23)
    retransmission=fact.iloc[[0]].copy()
    retransmission["ingested_at"]=retransmission.sale_at+pd.Timedelta(hours=25)
    pd.concat([fact,retransmission],ignore_index=True).to_parquet(tmp_path/"sales_fact.parquet",index=False)
    quality,_,_=SalesEngine(data_dir=tmp_path).quality(SalesRequest(),SCOPE)
    assert quality["events"]=={"raw_rows":21,"unique_lines":20,"late_lines":0}


@pytest.mark.parametrize("damage",["orphan","conflict","dimension","null"])
def test_sales_integrity_failures_withhold_numbers(tmp_path,damage):
    from scripts.generate_sales_data import generate
    generate(tmp_path,orders=10)
    fact=pd.read_parquet(tmp_path/"sales_fact.parquet")
    if damage=="orphan": fact.loc[0,"product_id"]=999
    elif damage=="conflict":
        duplicate=fact.iloc[[0]].copy(); duplicate["gross_cents"]+=10
        fact=pd.concat([fact,duplicate],ignore_index=True)
    elif damage=="null": fact.loc[0,"units_sold"]=None
    else:
        dim=pd.read_parquet(tmp_path/"product_dim.parquet")
        pd.concat([dim,dim.iloc[[0]]]).to_parquet(tmp_path/"product_dim.parquet",index=False)
    fact.to_parquet(tmp_path/"sales_fact.parquet",index=False)
    agent=PlatformAgent(sales_skills=SalesSkills(SalesEngine(data_dir=tmp_path)),scope=SCOPE)
    answer=agent.run(SALES_DEMOS[0],mode="demo")
    assert answer.status=="error" and not answer.results
    assert any(event["status"]=="error" for event in answer.trace)


def test_sales_llm_tool_validation_and_numerical_fabrication(engine):
    plan=parse_sales(SALES_DEMOS[0])
    manager=Mock(actual_provider="ollama",last_fallback_reason=None)
    manager.chat.return_value=ModelReply(model="test",latency_ms=1,content="99999999999 sales",tool_calls=[ToolCall(name="plan_sales",arguments=plan.model_dump(mode="json"))])
    answer=PlatformAgent(sales_skills=SalesSkills(engine),scope=SCOPE).run(SALES_DEMOS[0],mode="ollama",manager=manager)
    assert answer.status=="ok" and "99999999999" not in " ".join(answer.findings)
    manager.chat.return_value=ModelReply(model="test",latency_ms=1,tool_calls=[ToolCall(name="execute_sql",arguments={"sql":"SELECT 1"})])
    answer=PlatformAgent(sales_skills=SalesSkills(engine),scope=SCOPE).run(SALES_DEMOS[0],mode="openai",manager=manager)
    assert answer.status=="error" and not answer.results


def test_public_sales_blocks_providers_and_uses_registered_synthetic_source(engine):
    settings=replace(load_settings(),public_demo_enabled=True)
    manager=Mock(last_fallback_reason=None)
    agent=PlatformAgent(sales_skills=SalesSkills(engine),scope=SCOPE,settings=settings)
    assert agent.run(SALES_DEMOS[0],mode="openai",manager=manager).status=="error"
    manager.chat.assert_not_called()
    assert agent.run(SALES_DEMOS[0],mode="demo").status=="ok"
    assert set(domain_registry())=={"usage","sales"}
