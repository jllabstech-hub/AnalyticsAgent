"""Independent pandas oracle. Does not import the query engine, skills, or agent."""
import json
import pandas as pd
from scripts.generate_data import ROOT


def calculate(users, events, members, devices, metric, start, end, filters):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    population = users[users.registered_at < end].merge(members[(members.eligible_from < end) & (members.eligible_to > start)], on="user_id")
    snapshot = devices[(devices.valid_from < end) & (devices.valid_to > start if metric == "service_adoption_rate" else devices.valid_to >= end)]
    columns = ["user_id","device_model"] + (["valid_from","valid_to"] if metric == "service_adoption_rate" else [])
    population = population.merge(snapshot[columns], on="user_id", validate="many_to_many" if metric == "service_adoption_rate" else "many_to_one")
    if metric == "service_adoption_rate":
        population = population[(population.eligible_from < population.valid_to) & (population.valid_from < population.eligible_to) & (population.registered_at < population.valid_to)]
    active = events[(events.event_at >= start) & (events.event_at < end)].merge(users, on="user_id", validate="many_to_one")
    active = active.merge(devices, on=["user_id", "device_id"], validate="many_to_one")
    for key, value in filters.items():
        population = population[population[key] == value]
        active = active[active[key] == value]
    if metric == "mau":
        return float(active.user_id.nunique())
    if metric == "dau":
        daily = active.groupby(active.event_at.dt.normalize()).user_id.nunique()
        return float(daily.reindex(pd.date_range(start, end - pd.Timedelta(days=1)), fill_value=0).mean())
    if metric == "active_existing_users":
        return float(active.loc[active.registered_at < start, "user_id"].nunique())
    if metric == "service_adoption_rate":
        denominator = population.user_id.nunique()
        return float(active.user_id.nunique() / denominator) if denominator else None
    new = population[(population.registered_at >= start) & (population.registered_at < end)]
    if metric == "new_users":
        return float(new.user_id.nunique())
    denominator = new.user_id.nunique()
    numerator = new[(new.activated_at >= start) & (new.activated_at < end)].user_id.nunique()
    return float(numerator / denominator) if denominator else None


def build():
    folder = ROOT / "data" / "synthetic"
    users, events, members, devices = [pd.read_parquet(folder / f"{x}.parquet") for x in ["users", "service_activity", "service_membership", "device_mapping"]]
    events = events.drop_duplicates("event_id")
    cases = []
    scopes = [{}, {"market": "Market A"}, {"market": "Market B"}, {"service": "Service Alpha"}, {"device_model": "Nova Mini"}]
    for metric in ["mau", "dau", "new_users", "active_existing_users", "activation_rate", "service_adoption_rate"]:
        for index, filters in enumerate(scopes):
            baseline = calculate(users, events, members, devices, metric, "2026-08-01", "2026-09-01", filters)
            current = calculate(users, events, members, devices, metric, "2026-09-01", "2026-10-01", filters)
            cases.append({"id": f"{metric}-{index}", "question": f"Compare August and September {metric} for {filters or 'all users'}",
                          "metric": metric, "filters": filters, "baseline": baseline, "current": current})
    fixture = ROOT / "tests" / "fixtures"
    fixture.mkdir(exist_ok=True)
    (fixture / "reference_answers.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    (fixture / "expected_patterns.json").write_text(json.dumps({"seed": 20260701, "decline_market": "Market A", "growth_market": "Market B", "reduced_device": "Nova Mini", "incomplete_scenario": "incomplete", "references": len(cases)}, indent=2), encoding="utf-8")
    print(f"Saved {len(cases)} independent pandas comparison references.")


if __name__ == "__main__":
    build()
