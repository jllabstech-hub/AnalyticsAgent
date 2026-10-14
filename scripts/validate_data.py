"""Independent pandas integrity and quality checks, not runtime agent code."""
import argparse
import json
from pathlib import Path
import pandas as pd
from scripts.generate_data import ROOT


def validate(folder: Path) -> dict:
    tables = {p.stem: pd.read_parquet(p) for p in folder.glob("*.parquet")}
    users, events, membership, devices = (tables[x] for x in ["users", "service_activity", "service_membership", "device_mapping"])
    assert users.user_id.is_unique and users.account_id.is_unique
    assert users.market.isin(tables["market_reference"].market).all()
    assert (users.activated_at.dropna() >= users.set_index("user_id").loc[users.activated_at.notna(), "registered_at"].to_numpy()).all()
    for frame in [events, membership, devices]:
        assert frame.user_id.isin(users.user_id).all()
    assert not membership.duplicated(["user_id", "service"]).any()
    ordered = devices.sort_values(["user_id", "valid_from"])
    previous_end = ordered.groupby("user_id").valid_to.shift()
    assert ((previous_end.isna()) | (previous_end <= ordered.valid_from)).all()
    clean = events.drop_duplicates("event_id")
    joined = clean.merge(users[["user_id", "registered_at", "activated_at"]], on="user_id", validate="many_to_one")
    assert (joined.event_at >= joined.activated_at).all()
    assert (joined.ingested_at >= joined.event_at).all()
    member_join = clean.merge(membership, on=["user_id", "service"], validate="many_to_one")
    assert ((member_join.event_at >= member_join.eligible_from) & (member_join.event_at < member_join.eligible_to)).all()
    mapped = clean.merge(devices, on=["user_id", "device_id"], validate="many_to_one")
    assert ((mapped.event_at >= mapped.valid_from) & (mapped.event_at < mapped.valid_to)).all()
    assert clean.event_at.min() >= pd.Timestamp("2026-07-01")
    assert clean.event_at.max() < pd.Timestamp("2026-10-01")
    partial = pd.read_parquet(folder / "incomplete" / "service_activity.parquet")
    report = {"row_counts": {k: len(v) for k, v in tables.items()}, "unique_users": int(users.user_id.nunique()),
        "event_rows": len(events), "unique_events": len(clean), "duplicate_rows": len(events) - len(clean),
        "late_events_over_24h": int(((clean.ingested_at - clean.event_at).dt.total_seconds() > 86400).sum()),
        "market_distribution": users.market.value_counts().sort_index().to_dict(),
        "monthly_active_users": clean.groupby(clean.event_at.dt.strftime("%Y-%m")).user_id.nunique().to_dict(),
        "incomplete_september_days": int(partial.loc[partial.event_at.dt.month == 9, "event_at"].dt.normalize().nunique()),
        "primary_comparison_complete": bool(tables["data_quality_status"].query("scenario == 'primary'").complete.all()),
        "integrity": "pass"}
    assert report["primary_comparison_complete"]
    assert report["duplicate_rows"] > 0 and report["late_events_over_24h"] > 0
    (folder / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "synthetic")
    print(json.dumps(validate(parser.parse_args().data), indent=2))
