"""Reproducible fictional sales facts; money is stored as integer USD cents."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from analytics_agent.config import PROJECT_ROOT

SEED = 20260401
TABLES = ("sales_fact", "product_dim", "market_dim", "calendar_dim", "data_quality_status")


def generate(output=None, orders=25000, seed=SEED):
    output = Path(output or PROJECT_ROOT / "data" / "synthetic_sales")
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    products = pd.DataFrame({"product_id":range(1, 5), "product_name":["Orion One", "Orion Plus", "Nova Mini", "Nova Fold"],
        "category":["Fictional Phone"] * 4, "list_price_cents":[65000, 85000, 35000, 110000]})
    markets = pd.DataFrame({"market_id":range(1, 6), "market":[f"Market {c}" for c in "ABCDE"], "region":["Fictional Region"] * 5})
    days = pd.date_range("2026-04-01", "2026-09-30", freq="D")
    calendar = pd.DataFrame({"sale_date":days, "year":days.year, "month":days.month,
        "quarter":days.quarter, "month_label":days.strftime("%Y-%m"), "fiscal_year":days.year, "fiscal_quarter":days.quarter})
    # Each order has two lines and one date/market/channel; product groups can overlap.
    order_days = rng.integers(0, len(days), orders)
    order_market = rng.integers(1, 6, orders)
    channel = rng.choice(["Fictional Web", "Fictional Shops", "Fictional Partners"], orders)
    count = orders * 2
    sale_dates = days[np.repeat(order_days, 2)]
    product_id = rng.integers(1, 5, count)
    market_id = np.repeat(order_market, 2)
    units = rng.integers(1, 5, count)
    growing = (sale_dates.month >= 7) & (market_id == 1) & (product_id == 1)
    units[growing] += 2
    declining = (sale_dates.month >= 7) & (market_id == 4)
    units[declining] = np.maximum(1, units[declining] - 1)
    gross = products.list_price_cents.to_numpy()[product_id - 1] * units
    discounts = gross * rng.integers(0, 16, count) // 100
    returned = np.where(rng.random(count) < .08, rng.integers(1, 3, count), 0)
    returned = np.minimum(returned, units)
    returns = (gross - discounts) * returned // units
    adjustment = rng.integers(-100, 101, count)
    adjustment = np.maximum(adjustment, -(gross - discounts - returns))
    sale_at = sale_dates + pd.to_timedelta(rng.integers(0, 24*60*60, count), unit="s")
    late = rng.random(count) < .04
    ingestion_hours = np.where(late, rng.integers(25, 145, count), rng.integers(0, 24, count))
    fact = pd.DataFrame({"sales_line_id":[f"SYN-L{i:06}" for i in range(count)],
        "order_id":np.repeat([f"SYN-O{i:06}" for i in range(orders)], 2), "product_id":product_id,
        "market_id":market_id, "channel":np.repeat(channel, 2), "sale_date":sale_dates,
        "sale_at":sale_at, "units_sold":units, "returned_units":returned, "gross_cents":gross,
        "discount_cents":discounts, "return_cents":returns, "adjustment_cents":adjustment,
        "currency":["USD"]*count, "ingested_at":sale_at + pd.to_timedelta(ingestion_hours, unit="h")})
    duplicates = fact.sample(n=max(1, count//100), random_state=seed).copy()
    duplicates["ingested_at"] += pd.Timedelta(hours=1)
    fact = pd.concat([fact, duplicates], ignore_index=True).sample(frac=1, random_state=seed).reset_index(drop=True)
    tables = {"sales_fact":fact, "product_dim":products, "market_dim":markets, "calendar_dim":calendar}
    quality = []
    for scenario in ("primary", "incomplete"):
        for table in TABLES:
            for start in pd.date_range("2026-04-01", "2026-09-01", freq="MS"):
                end = start + pd.offsets.MonthBegin(1)
                complete = not (scenario == "incomplete" and table == "sales_fact" and start.month == 9)
                quality.append({"scenario":scenario, "dataset":table, "period_start":start, "period_end":end,
                    "available_through":end if complete else pd.Timestamp("2026-09-24"), "complete":complete,
                    "loaded_at":pd.Timestamp("2026-10-09"), "snapshot_as_of":pd.Timestamp("2026-10-10"),
                    "status":"complete" if complete else "intentional demonstration gap"})
    tables["data_quality_status"] = pd.DataFrame(quality)
    for name, frame in tables.items(): frame.to_parquet(output / f"{name}.parquet", index=False)
    incomplete = output / "incomplete"
    incomplete.mkdir(exist_ok=True)
    fact[fact.sale_date < pd.Timestamp("2026-09-24")].to_parquet(incomplete / "sales_fact.parquet", index=False)
    manifest = {"is_synthetic":True, "domain":"sales", "seed":seed, "unique_orders":orders,
        "period_start":"2026-04-01", "period_end_exclusive":"2026-10-01", "relative_period_anchor":"2026-10-01",
        "timezone":"UTC", "currency":"USD", "fiscal_year_start_month":1,
        "source_grain":"one invoiced order line; physical duplicates identified by sales_line_id",
        "row_counts":{name:len(frame) for name,frame in tables.items()}, "unique_sales_lines":count,
        "incomplete_scenario":"separate partition omits September 24–30; primary Q2/Q3 complete"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


if __name__ == "__main__": print(json.dumps(generate(), indent=2))
