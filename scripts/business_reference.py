"""Independent pandas oracle for new domains; never imported by runtime agents."""
import json
from pathlib import Path
import pandas as pd
from analytics_agent.config import PROJECT_ROOT


def load(domain,data_dir=None):
    if domain not in ("marketing","finance"): raise ValueError("Unknown reference domain")
    root=Path(data_dir or PROJECT_ROOT/"data"/f"synthetic_{domain}")
    fact_name=f"{domain}_fact"; entity_name="campaign_dim" if domain=="marketing" else "department_dim"
    frames={name:pd.read_parquet(root/f"{name}.parquet") for name in (fact_name,entity_name,"market_dim","calendar_dim","data_quality_status")}
    raw=frames[fact_name]
    assert not raw.drop(columns="ingested_at").drop_duplicates().event_id.duplicated().any()
    data=raw.sort_values("ingested_at").drop_duplicates("event_id")
    for name,key in ((entity_name,"entity_id"),("market_dim","market_id"),("calendar_dim","activity_date")):
        assert frames[name][key].notna().all() and not frames[name][key].duplicated().any()
        assert data[key].isin(frames[name][key]).all()
    data=data.merge(frames[entity_name],on="entity_id",validate="many_to_one").merge(frames["market_dim"],on="market_id",validate="many_to_one")
    assert frames['market_dim'].market.isin([f'Market {c}' for c in 'ABCDE']).all()
    assert data.activity_date.eq(data.activity_at.dt.normalize()).all()
    assert data.activity_at.ge(data.valid_from).all() and data.activity_at.lt(data.valid_to).all()
    assert data.ingested_at.ge(data.activity_at).all() and data.currency.eq("USD").all()
    if domain=="marketing":
        assert data.impressions.eq(1).all() and data.clicks.between(0,1).all() and data.conversions.between(0,data.clicks).all()
        assert data.spend_cents.ge(0).all()
        assert data.channel.isin(["Channel Search","Channel Social","Channel Email"]).all()
    else:
        assert data.revenue_cents.ge(0).all() and data.expense_cents.ge(0).all()
        assert ((data.category.eq("Revenue")&data.revenue_cents.gt(0)&data.expense_cents.eq(0))|
                (data.category.isin(["Cost of Goods","Operating Expense"])&data.revenue_cents.eq(0)&data.expense_cents.gt(0))).all()
    q=frames["data_quality_status"]
    assert not q.duplicated(["scenario","dataset","period_start"]).any()
    primary=q[q.scenario.eq("primary")]
    assert len(primary)==30 and primary.complete.all() and primary.available_through.eq(primary.period_end).all()
    report={"status":"pass","domain":domain,"row_counts":{name:len(frame) for name,frame in frames.items()},"canonical_rows":len(data),
        "duplicate_rows":len(raw)-len(data),"late_canonical_rows":int(((data.ingested_at-data.activity_at)>pd.Timedelta(hours=24)).sum()),
        "market_distribution":data.groupby("market").size().to_dict(),"monthly_rows":data.groupby(data.activity_date.dt.strftime("%Y-%m")).size().to_dict(),
        "join_cardinality":"pass","primary_Q2_Q3_complete":True,"quality_scenario":"separate incomplete September partition"}
    return data,report


def value(data,domain,metric,start,end,filters):
    selected=data[(data.activity_date>=start)&(data.activity_date<end)]
    for field,expected in filters.items(): selected=selected[selected[{"entity":"entity_name"}.get(field,field)].eq(expected)]
    if domain=="marketing":
        impressions=int(selected.impressions.sum()); clicks=int(selected.clicks.sum()); conversions=int(selected.conversions.sum()); cents=int(selected.spend_cents.sum())
        values={"impressions":impressions,"clicks":clicks,"conversions":conversions,"marketing_spend":cents/100,
            "click_through_rate":clicks/impressions if impressions else None,"conversion_rate":conversions/clicks if clicks else None,"cost_per_click":cents/100/clicks if clicks else None}
    else:
        revenue=int(selected.revenue_cents.sum()); expenses=int(selected.expense_cents.sum())
        values={"finance_revenue":revenue/100,"expenses":expenses/100,"profit":(revenue-expenses)/100,"profit_margin":(revenue-expenses)/revenue if revenue else None}
    return values[metric]


def generate_references():
    cases=[]; reports={}
    for domain in ("marketing","finance"):
        data,report=load(domain);reports[domain]=report
        metrics=["impressions","clicks","conversions","marketing_spend","click_through_rate","conversion_rate","cost_per_click"] if domain=="marketing" else ["finance_revenue","expenses","profit","profit_margin"]
        filters=[{}, {"market":"Market A"},{"market":"Market B"},{"entity":"Campaign Aurora" if domain=="marketing" else "Department Boreal"},
            {"market":"Market C","channel":"Channel Email"} if domain=="marketing" else {"market":"Market C","category":"Operating Expense"}]
        for metric in metrics:
            for index,selected in enumerate(filters):
                cases.append({"id":f"{domain}-{metric}-{index}","domain":domain,"metric":metric,"filters":selected,
                    "baseline":value(data,domain,metric,"2026-04-01","2026-07-01",selected),"current":value(data,domain,metric,"2026-07-01","2026-10-01",selected)})
        (PROJECT_ROOT/"data"/f"synthetic_{domain}"/"validation_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    (PROJECT_ROOT/"tests"/"fixtures"/"business_reference_answers.json").write_text(json.dumps(cases,indent=2)+"\n",encoding="utf-8")
    return reports


if __name__=="__main__": print(json.dumps(generate_references(),indent=2))
