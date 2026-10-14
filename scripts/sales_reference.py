"""Independent pandas validation/reference oracle. Never imported by runtime code."""
import json
from pathlib import Path
import pandas as pd
from analytics_agent.config import PROJECT_ROOT


def load(data_dir=None):
    root = Path(data_dir or PROJECT_ROOT / "data" / "synthetic_sales")
    frames = {name:pd.read_parquet(root / f"{name}.parquet") for name in
        ("sales_fact", "product_dim", "market_dim", "calendar_dim", "data_quality_status")}
    fact = frames["sales_fact"]
    signature = fact.drop(columns="ingested_at").drop_duplicates()
    assert not signature.sales_line_id.duplicated().any(), "Conflicting duplicate lines"
    fact = fact.sort_values("ingested_at").drop_duplicates("sales_line_id")
    for name, key in (("product_dim","product_id"),("market_dim","market_id"),("calendar_dim","sale_date")):
        assert not frames[name][key].duplicated().any(), f"Nonunique {name} key"
        assert fact[key].isin(frames[name][key]).all(), f"Orphan {name} foreign key"
    assert (fact.sale_at.dt.normalize() == fact.sale_date).all()
    assert (fact.ingested_at >= fact.sale_at).all()
    assert fact.currency.eq("USD").all()
    assert fact.channel.isin(["Fictional Web","Fictional Shops","Fictional Partners"]).all()
    assert ((fact.units_sold > 0) & (fact.returned_units.between(0, fact.units_sold))).all()
    assert (fact.discount_cents.between(0, fact.gross_cents)).all()
    assert (fact.return_cents.between(0, fact.gross_cents-fact.discount_cents)).all()
    assert not fact.groupby("order_id")[["market_id","sale_date","channel"]].nunique().gt(1).any().any()
    fact["net_cents"] = fact.gross_cents - fact.discount_cents - fact.return_cents + fact.adjustment_cents
    assert fact.net_cents.ge(0).all()
    joined = fact.merge(frames["product_dim"], on="product_id",validate="many_to_one").merge(
        frames["market_dim"],on="market_id",validate="many_to_one")
    primary=frames["data_quality_status"].query("scenario == 'primary'")
    assert not frames["data_quality_status"].duplicated(["scenario","dataset","period_start"]).any()
    certified=bool(primary.complete.all() and (primary.available_through==primary.period_end).all() and len(primary)==30)
    assert certified, "Primary sales coverage must be complete"
    report = {"status":"pass", "row_counts":{name:len(frame) for name,frame in frames.items()},
        "unique_orders":fact.order_id.nunique(), "unique_sales_lines":len(fact),
        "duplicate_rows":len(frames["sales_fact"])-len(fact),
        "late_unique_lines":int(((fact.ingested_at-fact.sale_at)>pd.Timedelta(hours=24)).sum()),
        "market_distribution":joined.groupby("market").size().to_dict(),
        "monthly_net_cents":joined.groupby(joined.sale_date.dt.strftime("%Y-%m")).net_cents.sum().to_dict(),
        "join_cardinality":"pass", "money_grain":"integer USD cents", "primary_Q2_Q3_complete":certified,
        "quality_demonstration":"separate incomplete sales partition omits September 24–30"}
    return joined, report


def value(data, metric, start, end, filters):
    selected = data[(data.sale_date >= start) & (data.sale_date < end)]
    for field, expected in filters.items():
        selected = selected[selected[{"product":"product_name"}.get(field,field)].eq(expected)]
    cents = int(selected.net_cents.sum())
    orders = int(selected.order_id.nunique())
    result = {"net_sales":cents/100, "units_sold":int(selected.units_sold.sum()), "orders":orders,
        "avg_order_value":cents/100/orders if orders else None}[metric]
    return {"value":result, "net_cents":cents, "orders":orders, "units_sold":int(selected.units_sold.sum())}


def generate_references(data_dir=None, output=None):
    data, report = load(data_dir)
    filters = [{}, {"market":"Market A"}, {"market":"Market B"}, {"product":"Orion One"},
        {"product":"Nova Mini"}, {"market":"Market A","product":"Orion One"},
        {"channel":"Fictional Web"}, {"market":"Market D"}, {"product":"Nova Fold"},
        {"market":"Market E","channel":"Fictional Partners"}]
    cases = []
    for metric in ("net_sales","units_sold","orders","avg_order_value"):
        for index, selected in enumerate(filters):
            baseline = value(data,metric,"2026-04-01","2026-07-01",selected)
            current = value(data,metric,"2026-07-01","2026-10-01",selected)
            cases.append({"id":f"sales-{metric}-{index}", "metric":metric, "filters":selected,
                "baseline":baseline, "current":current})
    destination = Path(output or PROJECT_ROOT / "tests" / "fixtures" / "sales_reference_answers.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(cases,indent=2)+"\n",encoding="utf-8")
    data_root = Path(data_dir or PROJECT_ROOT / "data" / "synthetic_sales")
    (data_root / "validation_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report


if __name__ == "__main__": print(json.dumps(generate_references(),indent=2))
