"""Marketing/Finance comparison and contribution with shared numerical checks."""
import math
import time
from analytics_agent.business_engine import BusinessEngine, business_definitions, COUNTERS
from analytics_agent.business_models import BusinessResult
from analytics_agent.skills import changes


def business_changes(baseline,current):
    delta,percent=changes(baseline,current)
    return delta,percent if baseline is not None and baseline>0 else None


class BusinessSkills:
    names={"M1":"Marketing Metric Comparison","M2":"Marketing Contribution Breakdown","F1":"Finance Metric Comparison","F2":"Finance Contribution Breakdown"}

    def __init__(self,domain,engine=None):
        self.domain=domain;self.engine=engine or BusinessEngine(domain)
        if self.engine.domain!=domain:raise ValueError("Adapter domain mismatch")

    def query_plan(self,plan,scope):
        required=["K1","K2"] if plan.operation=="investigation" else ["K2"] if plan.operation=="contribution" else ["K1"]
        if any(skill not in scope.skills for skill in required):raise PermissionError("Operation outside approved skill permissions.")
        self.engine.authorize(plan.request,scope)
        kinds=["total"]
        if plan.operation in ("comparison","investigation"):kinds.append("trend")
        if plan.operation in ("contribution","investigation"):kinds.append("breakdown")
        return [self.engine.prepare(plan.request,scope,kind,period,plan.dimension) for kind in kinds for period in ("baseline","current")]

    def execute(self,plan,scope,bound_queries=None,knowledge=None):
        started=time.perf_counter();queries=self.query_plan(plan,scope)
        if bound_queries is not None and bound_queries!=queries:raise PermissionError("Prepared domain plan was modified.")
        quality,warnings,evidence=self.engine.quality(plan.request,scope);outputs={}
        for query in queries:
            rows,item=self.engine.execute_bound(query,scope);evidence.append(item);outputs[(query.kind,query.period)]=rows
        left=outputs[("total","baseline")][0];right=outputs[("total","current")][0]
        baseline,current=left['value'],right['value']
        definition=business_definitions(self.domain)[plan.request.metric].model_dump()
        if any(v is not None and not math.isfinite(v) for v in (baseline,current)):raise ValueError("Nonfinite analytical result")
        if definition['denominator'] and (baseline is None or current is None):warnings.append("Zero denominator: the metric is undefined rather than zero.")
        if baseline is not None and baseline<=0:warnings.append("Relative percentage change is undefined for a zero or negative baseline.")
        trend=[]
        for period in ("baseline","current"):
            monthly=outputs.get(("trend",period))
            if monthly is None:continue
            total=left if period=="baseline" else right
            if any(sum(r[field] for r in monthly)!=total[field] for field in COUNTERS[self.domain]):raise ValueError("Monthly counter or money reconciliation failed.")
            for row in monthly:
                month=row['group_name']
                complete=quality['complete'] or not any(r['dataset']==self.engine.fact and not r['complete'] and r['period_start'].strftime('%Y-%m')==month for r in quality['coverage'])
                trend.append({'period':period,'month':month,'value':row['value'],'coverage_complete':complete,**{field:row[field] for field in COUNTERS[self.domain]}})
        records=[];reconciliation={}
        if ("breakdown","baseline") in outputs:
            lmap={r['group_name']:r['value'] for r in outputs[('breakdown','baseline')]};rmap={r['group_name']:r['value'] for r in outputs[('breakdown','current')]}
            for group in sorted(set(lmap)|set(rmap)):
                b=lmap.get(group,0 if definition['additive'] else None);c=rmap.get(group,0 if definition['additive'] else None)
                delta,percent=business_changes(b,c)
                records.append({'group':group,'baseline':b,'current':c,'change':delta,'percentage_change':percent})
            additive=definition['additive']
            exclusive=all(r['baseline'] is not None and r['current'] is not None for r in records)
            reconciled=additive and exclusive and math.isclose(sum(r['baseline'] for r in records),baseline,abs_tol=1e-6) and math.isclose(sum(r['current'] for r in records),current,abs_tol=1e-6)
            if additive and not reconciled:raise ValueError("Exclusive group amounts failed reconciliation.")
            reconciliation={'additive':additive,'mutually_exclusive':True,'reconciled':reconciled,'sum_group_changes':sum(r['change'] for r in records) if reconciled else None,'total_change':business_changes(baseline,current)[0]}
            if not additive:warnings.append("Group ratios are not additive; total ratios use summed numerators and denominators.")
        delta,percent=business_changes(baseline,current)
        common=dict(request=plan.request,definition=definition,baseline=baseline,current=current,absolute_change=delta,percentage_change=percent,
            warnings=warnings,quality=quality,evidence=evidence,queries=[q.model_dump(mode='json') for q in queries],duration_ms=round((time.perf_counter()-started)*1000,3))
        prefix='M' if self.domain=='marketing' else 'F';results=[]
        if plan.operation in ('comparison','investigation'):results.append(BusinessResult(skill=prefix+'1',trend=trend,**common))
        if plan.operation in ('contribution','investigation'):results.append(BusinessResult(skill=prefix+'2',records=records,reconciliation=reconciliation,**common))
        if sum(len(r.trend)+len(r.records) for r in results)>self.engine.result_limit:raise ValueError("Result exceeds configured row limit.")
        return results
