"""Reproducible fictional warehouse. Never imported by the analytical agent."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ["Service Alpha", "Service Beta", "Service Gamma"]
MODELS = ["Orion One", "Orion Plus", "Nova Mini", "Nova Fold"]


def generate(output: Path, n: int = 100_000, seed: int = 20260701) -> dict:
    rng = np.random.default_rng(seed)
    fake = Faker()
    fake.seed_instance(seed)
    output.mkdir(parents=True, exist_ok=True)
    ids = np.arange(n)
    registered = pd.Timestamp("2026-01-01") + pd.to_timedelta(rng.integers(0, 273, n), unit="D")
    activated = registered + pd.to_timedelta(rng.integers(0, 11, n), unit="D")
    activated = pd.Series(activated).where(rng.random(n) < .87)
    users = pd.DataFrame({"user_id": ids, "account_id": [f"SYN-ACCOUNT-{i:06}" for i in ids],
                          "display_name": [f"Fictional-{fake.word()}-{i}" for i in ids],
                          "market": rng.choice([f"Market {x}" for x in "ABCDE"], n),
                          "registered_at": registered, "activated_at": activated})
    model = rng.choice(MODELS, n)
    device = pd.DataFrame({"user_id": ids, "device_id": [f"SYN-DEVICE-{i:06}" for i in ids],
                           "device_model": model, "valid_from": registered,
                           "valid_to": pd.Timestamp("2026-10-01")})
    switches = (rng.random(n) < .04) & (registered < pd.Timestamp("2026-08-01"))
    old = device.loc[switches].copy()
    device.loc[switches, "valid_from"] = pd.Timestamp("2026-08-01")
    device.loc[switches, "device_model"] = rng.choice(MODELS, switches.sum())
    old["valid_to"] = pd.Timestamp("2026-08-01")
    old["device_id"] += "-OLD"
    device = pd.concat([device, old], ignore_index=True)
    members = []
    for service, probability in zip(SERVICES, [1, .65, .4]):
        chosen = rng.random(n) < probability
        members.append(pd.DataFrame({"user_id": ids[chosen], "service": service,
            "eligible_from": registered[chosen], "eligible_to": pd.Timestamp("2026-10-01"),
            "membership_cohort": rng.choice(["Standard", "Premium"], chosen.sum())}))
    membership = pd.concat(members, ignore_index=True)
    events = []
    for month in [7, 8, 9]:
        start, end = pd.Timestamp(2026, month, 1), pd.Timestamp(2026, month, 1) + pd.offsets.MonthBegin(1)
        current_devices = device[(device.valid_from < end) & (device.valid_to > start)].sort_values("valid_from").drop_duplicates("user_id", keep="last")
        pool = membership.merge(users, on="user_id", validate="many_to_one").merge(current_devices[["user_id", "device_id", "device_model"]], on="user_id", validate="many_to_one")
        chance = np.full(len(pool), .68 if month == 8 else .66)
        if month == 9:
            chance[(pool.market == "Market A") & (pool.registered_at < start)] *= .47
            chance[pool.market == "Market B"] *= 1.2
            chance[(pool.device_model == "Nova Mini") & (pool.registered_at < start)] *= .63
        chosen = pool[(rng.random(len(pool)) < chance) & pool.activated_at.notna() & (pool.activated_at < end)].copy()
        repeats = rng.integers(2, 7, len(chosen))
        chosen = chosen.loc[chosen.index.repeat(repeats)].reset_index(drop=True)
        earliest = chosen.activated_at.clip(lower=start).astype("datetime64[ns]").astype("int64").to_numpy()
        latest = end.value
        timestamps = pd.to_datetime(earliest + ((latest - earliest) * rng.random(len(chosen))).astype("int64"))
        frame = chosen[["user_id", "service", "device_id"]].copy()
        frame["event_at"] = timestamps
        frame["event_type"] = "usage"
        frame["ingested_at"] = timestamps + pd.to_timedelta(np.where(rng.random(len(frame)) < .02, 72, 1), unit="h")
        events.append(frame)
    activity = pd.concat(events, ignore_index=True)
    activity.insert(0, "event_id", [f"SYN-EVENT-{i:09}" for i in range(len(activity))])
    copies = activity.sample(frac=.005, random_state=seed).copy()
    activity = pd.concat([activity, copies], ignore_index=True)
    markets = pd.DataFrame({"market": [f"Market {x}" for x in "ABCDE"], "timezone": "UTC", "is_synthetic": True})
    tables = {"users": users, "service_activity": activity, "service_membership": membership,
              "device_mapping": device, "market_reference": markets}
    for name, frame in tables.items():
        frame.to_parquet(output / f"{name}.parquet", index=False)
    incomplete = output / "incomplete"
    incomplete.mkdir(exist_ok=True)
    partial = activity[activity.event_at < pd.Timestamp("2026-09-24")]
    partial.to_parquet(incomplete / "service_activity.parquet", index=False)
    quality = []
    for scenario in ["primary", "incomplete"]:
        for source in tables:
            for month in [7, 8, 9]:
                start = pd.Timestamp(2026, month, 1)
                end = start + pd.offsets.MonthBegin(1)
                complete = not (scenario == "incomplete" and source == "service_activity" and month == 9)
                quality.append({"scenario": scenario, "dataset": source, "period_start": start,
                    "period_end": end, "complete": complete, "available_through": end if complete else pd.Timestamp("2026-09-24"),
                    "loaded_at": pd.Timestamp("2026-10-04"), "snapshot_as_of": pd.Timestamp("2026-10-05"),
                    "status": "complete" if complete else "missing final seven days"})
    pd.DataFrame(quality).to_parquet(output / "data_quality_status.parquet", index=False)
    manifest = {"seed": seed, "user_count": n, "is_synthetic": True, "timezone": "UTC", "snapshot_as_of": "2026-10-05",
                "period_start": "2026-07-01", "period_end_exclusive": "2026-10-01"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "synthetic")
    parser.add_argument("--users", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260701)
    args = parser.parse_args()
    if args.users < 1:
        parser.error("--users must be positive")
    print(json.dumps(generate(args.output, args.users, args.seed), indent=2))
