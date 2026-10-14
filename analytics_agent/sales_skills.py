"""Sales skill operations use the same approved adapter in every execution mode."""
import math
import time
from analytics_agent.sales_engine import SalesEngine, sales_definitions
from analytics_agent.sales_models import SalesResult
from analytics_agent.skills import changes


class SalesSkills:
    names = {"S1":"Sales Metric Comparison", "S2":"Sales Contribution Breakdown"}

    def __init__(self, engine=None): self.engine = engine or SalesEngine()

    def query_plan(self, plan, scope):
        request=plan.request
        required = ["K1","K2"] if plan.operation == "investigation" else ["K2"] if plan.operation == "contribution" else ["K1"]
        if any(skill not in scope.skills for skill in required): raise PermissionError("Sales operation outside approved skill permissions.")
        self.engine.authorize(request,scope)
        kinds=["total"]
        if plan.operation in ("comparison","investigation"): kinds.append("trend")
        if plan.operation in ("contribution","investigation"): kinds.append("breakdown")
        return [self.engine.prepare(request,scope,kind,period,plan.dimension) for kind in kinds for period in ("baseline","current")]

    def execute(self, plan, scope, bound_queries=None, knowledge=None):
        started=time.perf_counter()
        queries=self.query_plan(plan,scope)
        if bound_queries is not None and bound_queries != queries: raise PermissionError("Prepared sales plan was modified.")
        quality,warnings,evidence=self.engine.quality(plan.request,scope)
        outputs={}
        for query in queries:
            rows,item=self.engine.execute_bound(query,scope)
            evidence.append(item)
            outputs[(query.kind,query.period)]=rows
        left=outputs[("total","baseline")][0]; right=outputs[("total","current")][0]
        base,now=left["value"],right["value"]
        if any(value is not None and not math.isfinite(value) for value in (base,now)): raise ValueError("Nonfinite sales value")
        if plan.request.metric == "avg_order_value" and (not left["orders"] or not right["orders"]):
            warnings.append("Zero orders: average order value is undefined, not zero.")
        trend=[]
        for period in ("baseline","current"):
            for row in outputs.get(("trend",period),[]):
                month=int(row["group_name"][-2:])
                month_complete=quality["complete"] or not any(r["dataset"]=="sales_fact" and not r["complete"] and r["period_start"].month==month for r in quality["coverage"])
                trend.append({"period":period,"month":row["group_name"],"value":row["value"],"net_sales":row["net_cents"]/100,
                    "units_sold":row["units_sold"],"orders":row["orders"],"coverage_complete":month_complete})
            if ("trend",period) in outputs:
                monthly=outputs[("trend",period)]
                total=left if period=="baseline" else right
                if any(sum(row[field] for row in monthly)!=total[field] for field in ("net_cents","units_sold","orders")):
                    raise ValueError("Monthly sales values failed reconciliation.")
        records=[]; reconciliation={}
        if ("breakdown","baseline") in outputs:
            lmap={r["group_name"]:r for r in outputs[("breakdown","baseline")]}
            rmap={r["group_name"]:r for r in outputs[("breakdown","current")]}
            for group in sorted(set(lmap)|set(rmap)):
                b=lmap.get(group,{}).get("value",None if plan.request.metric=="avg_order_value" else 0)
                c=rmap.get(group,{}).get("value",None if plan.request.metric=="avg_order_value" else 0)
                delta,percent=changes(b,c)
                records.append({"group":group,"baseline":b,"current":c,"change":delta,"percentage_change":percent})
            additive=plan.request.metric != "avg_order_value"
            exclusive=additive and base is not None and now is not None and all(r["baseline"] is not None and r["current"] is not None for r in records)
            exclusive=exclusive and math.isclose(sum(r["baseline"] for r in records),base,abs_tol=1e-6) and math.isclose(sum(r["current"] for r in records),now,abs_tol=1e-6)
            reconciliation={"additive":additive,"mutually_exclusive":exclusive,"reconciled":exclusive,
                "sum_group_changes":sum(r["change"] for r in records) if exclusive else None,"total_change":changes(base,now)[0]}
            if not exclusive: warnings.append("Distinct orders can overlap across products, and ratios are nonadditive; group deltas must not be summed.")
        delta,percent=changes(base,now)
        common=dict(request=plan.request,definition=(knowledge or {}).get("metric",sales_definitions()[plan.request.metric].model_dump()),
            baseline=base,current=now,absolute_change=delta,percentage_change=percent,warnings=warnings,quality=quality,
            evidence=evidence,queries=[q.model_dump(mode="json") for q in queries],duration_ms=round((time.perf_counter()-started)*1000,3))
        results=[]
        if plan.operation in ("comparison","investigation"): results.append(SalesResult(skill="S1",trend=trend,**common))
        if plan.operation in ("contribution","investigation"): results.append(SalesResult(skill="S2",records=records,reconciliation=reconciliation,**common))
        if sum(len(r.trend)+len(r.records) for r in results)>self.engine.result_limit: raise ValueError("Sales result exceeds configured row limit.")
        return results
