"""Seeded fictional campaign observations and booked finance transactions."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from analytics_agent.config import PROJECT_ROOT


def generate(domain, output=None, rows=None, seed=None):
    if domain not in ("marketing", "finance"): raise ValueError("Unregistered generator domain")
    output=Path(output or PROJECT_ROOT / "data" / f"synthetic_{domain}")
    output.mkdir(parents=True,exist_ok=True)
    seed=seed if seed is not None else (20260402 if domain=="marketing" else 20260403)
    rows=rows if rows is not None else (60000 if domain=="marketing" else 30000)
    if rows<1: raise ValueError("Generate at least one event")
    rng=np.random.default_rng(seed)
    days=pd.date_range("2026-04-01","2026-09-30")
    dates=days[rng.integers(0,len(days),rows)]
    market_ids=rng.integers(1,6,rows)
    names=[f"Campaign {name}" for name in ("Aurora","Boreal","Cinder","Delta")] if domain=="marketing" else [f"Department {name}" for name in ("Aurora","Boreal","Cinder")]
    entity_ids=rng.integers(1,len(names)+1,rows)
    entities=pd.DataFrame({"entity_id":range(1,len(names)+1),"entity_name":names,"valid_from":pd.Timestamp("2026-04-01"),"valid_to":pd.Timestamp("2026-10-01")})
    fact=pd.DataFrame({"event_id":[f"SYN-{domain[:1].upper()}-{i:06}" for i in range(rows)],"entity_id":entity_ids,"market_id":market_ids,"activity_date":dates})
    fact["activity_at"]=dates+pd.to_timedelta(rng.integers(0,86400,rows),unit="s")
    late=rng.random(rows)<.05
    fact["ingested_at"]=fact.activity_at+pd.to_timedelta(np.where(late,rng.integers(25,97,rows),rng.integers(0,5,rows)),unit="h")
    fact["currency"]="USD"
    if domain=="marketing":
        fact["channel"]=rng.choice(["Channel Search","Channel Social","Channel Email"],rows)
        probability=np.where((dates.month>=7)&(entity_ids==1),.08,.14)
        probability=np.where((dates.month>=7)&(market_ids==2),.22,probability)
        fact["impressions"]=np.ones(rows,dtype=np.int64)
        fact["clicks"]=(rng.random(rows)<probability).astype(np.int64)
        fact["conversions"]=(fact.clicks.to_numpy().astype(bool)&(rng.random(rows)<.18)).astype(np.int64)
        fact["spend_cents"]=rng.integers(5,36,rows)
        entity_table="campaign_dim"
    else:
        categories=rng.choice(["Revenue","Cost of Goods","Operating Expense"],rows,p=[.5,.3,.2])
        amounts=rng.integers(10000,250001,rows)
        elevated=(dates.month>=7)&(entity_ids==2)&(categories!="Revenue")
        amounts[elevated]=amounts[elevated]*3//2
        fact["category"]=categories
        fact["revenue_cents"]=np.where(categories=="Revenue",amounts,0)
        fact["expense_cents"]=np.where(categories!="Revenue",amounts*3//5,0)
        entity_table="department_dim"
    duplicates=fact.sample(n=max(1,rows//100),random_state=seed).copy()
    duplicates["ingested_at"]+=pd.Timedelta(hours=1)
    fact=pd.concat([fact,duplicates],ignore_index=True).sample(frac=1,random_state=seed).reset_index(drop=True)
    tables={f"{domain}_fact":fact,entity_table:entities,
        "market_dim":pd.DataFrame({"market_id":range(1,6),"market":[f"Market {c}" for c in "ABCDE"]}),
        "calendar_dim":pd.DataFrame({"activity_date":days,"month_label":days.strftime("%Y-%m"),"quarter":days.quarter})}
    quality=[]
    for scenario in ("primary","incomplete"):
        for table in (*tables,"data_quality_status"):
            for start in pd.date_range("2026-04-01","2026-09-01",freq="MS"):
                end=start+pd.offsets.MonthBegin(1)
                complete=not(scenario=="incomplete" and table==f"{domain}_fact" and start.month==9)
                quality.append({"scenario":scenario,"dataset":table,"period_start":start,"period_end":end,"complete":complete,
                    "available_through":end if complete else pd.Timestamp("2026-09-24"),"loaded_at":pd.Timestamp("2026-10-09"),"snapshot_as_of":pd.Timestamp("2026-10-10")})
    tables["data_quality_status"]=pd.DataFrame(quality)
    for name,frame in tables.items(): frame.to_parquet(output/f"{name}.parquet",index=False)
    (output/"incomplete").mkdir(exist_ok=True)
    fact[fact.activity_date<pd.Timestamp("2026-09-24")].to_parquet(output/"incomplete"/f"{domain}_fact.parquet",index=False)
    manifest={"is_synthetic":True,"domain":domain,"seed":seed,"canonical_rows":rows,"row_counts":{name:len(frame) for name,frame in tables.items()},
        "period_start":"2026-04-01","period_end_exclusive":"2026-10-01","relative_period_anchor":"2026-10-01","timezone":"UTC","currency":"USD",
        "grain":"one impression observation" if domain=="marketing" else "one booked revenue or expense transaction; not a double-entry general ledger",
        "quality_scenario":"incomplete September 24–30 isolated from primary"}
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


if __name__=="__main__":
    print(json.dumps({domain:generate(domain) for domain in ("marketing","finance")},indent=2))
