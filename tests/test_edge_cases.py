"""Small independent hand-calculated warehouse for boundary and failure cases."""
import time
import pandas as pd
import pytest
from analytics_agent.engine import DEADLINE, Engine
from analytics_agent.models import AccessScope, AnalyticsRequest, Period
from analytics_agent.skills import SkillRegistry, ToolArguments


@pytest.fixture
def small(tmp_path):
    users = pd.DataFrame({"user_id":[0,1,2], "market":["Market A","Market A","Market B"],
        "registered_at":pd.to_datetime(["2026-07-31","2026-08-01","2026-09-01"]),
        "activated_at":pd.to_datetime(["2026-08-01","2026-08-01",None])})
    members = pd.DataFrame({"user_id":[0,1,2,0], "service":["Service Alpha"]*3+["Service Beta"],
        "eligible_from":pd.to_datetime(["2026-07-31","2026-08-01","2026-09-01","2026-07-31"]),
        "eligible_to":pd.to_datetime(["2026-10-01"]*4), "membership_cohort":["Standard","Standard","Standard","Premium"]})
    devices = pd.DataFrame({"user_id":[0,0,1,2], "device_id":["old","new","mini","inactive"],
        "device_model":["Orion One","Nova Fold","Nova Mini","Orion Plus"],
        "valid_from":pd.to_datetime(["2026-07-31","2026-09-15","2026-08-01","2026-09-01"]),
        "valid_to":pd.to_datetime(["2026-09-15","2026-10-01","2026-10-01","2026-10-01"])})
    events = pd.DataFrame({"event_id":["e0","e0","e1","e2","e3","e4"], "user_id":[0,0,1,0,0,0],
        "device_id":["old","old","mini","old","new","new"], "service":["Service Alpha"]*5+["Service Beta"],
        "event_at":pd.to_datetime(["2026-08-01 00:00:00","2026-08-01 00:00:00","2026-08-31 23:59:59","2026-09-01 00:00:00","2026-09-15 00:00:00","2026-09-30 23:59:59"]),
        "ingested_at":pd.to_datetime(["2026-08-02","2026-08-02","2026-09-01","2026-09-01","2026-09-15","2026-10-03"])})
    quality = pd.DataFrame({"scenario":["primary"],"dataset":["service_activity"],"period_start":pd.to_datetime(["2026-07-01"]),"period_end":pd.to_datetime(["2026-10-01"]),"complete":[True],"available_through":pd.to_datetime(["2026-10-01"]),"loaded_at":pd.to_datetime(["2026-10-04"]),"snapshot_as_of":pd.to_datetime(["2026-10-05"]),"status":["complete"]})
    tables = {"users":users,"service_membership":members,"device_mapping":devices,"service_activity":events,"data_quality_status":quality,"market_reference":pd.DataFrame({"market":["Market A","Market B"]})}
    for name, frame in tables.items(): frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    return Engine(tmp_path)


def test_distinct_users_duplicate_events_and_date_boundaries(small):
    request = AnalyticsRequest()
    assert small.metric(request,request.baseline)[0][0].value == 2
    assert small.metric(request,request.current)[0][0].value == 1
    first_day = Period(start="2026-08-01",end="2026-08-02")
    assert small.metric(request,first_day)[0][0].value == 1
    final_day = Period(start="2026-08-31",end="2026-09-01")
    assert small.metric(request,final_day)[0][0].value == 1


def test_zero_denominator_actual_sql_and_valid_zero_rate(small):
    request = AnalyticsRequest(metric="activation_rate",market="Market B")
    baseline = small.metric(request,request.baseline)[0][0]
    current = small.metric(request,request.current)[0][0]
    assert baseline.denominator == 0 and baseline.value is None
    assert current.denominator == 1 and current.value == 0


def test_time_valid_device_history_and_overlapping_groups(small):
    request = AnalyticsRequest()
    result = SkillRegistry(small).execute("K2",ToolArguments(request=request,dimension="device_model"))
    assert not result.reconciliation["reconciled"]
    models = {r["group"]:r for r in result.records}
    assert models["Orion One"]["current"] == 1 and models["Nova Fold"]["current"] == 1


def test_membership_cohorts_overlap_without_selected_service(small):
    result = SkillRegistry(small).execute("K3",ToolArguments(request=AnalyticsRequest(),cohort="membership"))
    assert not result.reconciliation["reconciled"]


def test_mean_dau_includes_zero_activity_days(small):
    request = AnalyticsRequest(metric="dau")
    assert small.metric(request,request.baseline)[0][0].value == pytest.approx(2/31)
    assert small.metric(request,request.current)[0][0].value == pytest.approx(3/30)


def test_temporal_join_multiplication_withholds_results(small):
    path = small.data_dir / "service_membership.parquet"
    members = pd.read_parquet(path)
    pd.concat([members,members.iloc[[0]]]).to_parquet(path,index=False)
    with pytest.raises(ValueError,match="Join-cardinality"):
        SkillRegistry(small).execute("K1",ToolArguments(request=AnalyticsRequest()))


def test_stale_snapshot_warning(small):
    path = small.data_dir / "data_quality_status.parquet"
    quality = pd.read_parquet(path)
    quality["loaded_at"] = pd.Timestamp("2026-10-01")
    quality.to_parquet(path,index=False)
    result = SkillRegistry(small).execute("K1",ToolArguments(request=AnalyticsRequest()))
    assert any("Stale snapshot" in w for w in result.warnings)


def test_result_limit_and_deadline_are_enforced(small):
    small.result_limit = 1
    request = AnalyticsRequest()
    with pytest.raises(ValueError,match="Result exceeds"):
        small.trend(request,Period(start="2026-08-01",end="2026-10-01"))
    token = DEADLINE.set(time.perf_counter()-1)
    try:
        with pytest.raises(TimeoutError): small.metric(request,request.current)
    finally: DEADLINE.reset(token)


def test_external_files_and_mutating_sql_are_rejected(small):
    secret = small.data_dir / "unapproved.csv"
    secret.write_text("private\nfictional-test-secret",encoding="utf-8")
    with small.session() as connection:
        with pytest.raises(Exception,match="disabled|Permission|permission"):
            connection.execute("SELECT * FROM read_csv(?)",[str(secret)])
        with pytest.raises(ValueError,match="read-only"):
            small._execute(connection,"DELETE FROM users",[],"unapproved",AnalyticsRequest())


def test_scope_keyed_cache_revalidates_permissions_and_returns_copies(small):
    request = AnalyticsRequest()
    value, evidence = small.metric(request,request.current)
    again, cached = small.metric(request,request.current)
    assert not evidence.cache_hit and cached.cache_hit
    assert again == value
    restricted, restricted_evidence = small.metric(request,request.current,AccessScope(markets=("Market B",)))
    assert restricted[0].value == 0 and not restricted_evidence.cache_hit
    with pytest.raises(PermissionError):
        small.metric(AnalyticsRequest(market="Market A"),request.current,AccessScope(markets=("Market B",)))
    cached.parameters["metric"] = "tampered"
    assert small.metric(request,request.current)[1].parameters["metric"] == "mau"


def test_cache_invalidates_when_data_changes(small):
    request = AnalyticsRequest()
    small.metric(request,request.current)
    path = small.data_dir / "service_activity.parquet"
    events = pd.read_parquet(path)
    events = events[events.event_at < pd.Timestamp("2026-09-01")]
    events.to_parquet(path,index=False)
    values, evidence = small.metric(request,request.current)
    assert values[0].value == 0 and not evidence.cache_hit


def test_missing_coverage_metadata_is_reported(small):
    path = small.data_dir / "data_quality_status.parquet"
    pd.read_parquet(path).iloc[:0].to_parquet(path,index=False)
    result = SkillRegistry(small).execute("K1",ToolArguments(request=AnalyticsRequest()))
    assert any("Missing or incomplete coverage" in w for w in result.warnings)
