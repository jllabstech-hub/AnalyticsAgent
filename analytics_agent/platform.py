"""Domain routing and observable component events; no hidden model reasoning."""
import json
import re
import time
from pathlib import Path
from functools import lru_cache
from typing import Literal
import yaml
from pydantic import Field
from analytics_agent.agent import AnalyticsAgent, AgentAnswer, ConversationContext, parse_demo
from analytics_agent.config import load_settings, PROJECT_ROOT
from analytics_agent.engine import DEADLINE
from analytics_agent.models import Contract, AccessScope, Domain
from analytics_agent.providers import ProviderError, manager_from_settings
from analytics_agent.sales_models import SalesContext, SalesPlan, SalesResult
from analytics_agent.sales_parser import parse_sales
from analytics_agent.sales_skills import SalesSkills
from analytics_agent.business_models import BusinessContext, BusinessPlan, BusinessResult
from analytics_agent.business_parser import parse_business
from analytics_agent.business_skills import BusinessSkills
from analytics_agent.skills import SkillResult, SkillRegistry

STAGES = ["User Query", "Intent Understanding", "Domain & Skill Selection", "Knowledge Retrieval",
    "Approved Query Generation", "Execute & Validate", "Results & Insights"]


class DomainDefinition(Contract):
    version: str = "1.0"
    skill_id: str
    name: str
    operations: tuple[str, ...]
    metrics: tuple[str, ...]
    source: str
    date_range: str


@lru_cache(maxsize=1)
def domain_registry():
    raw=yaml.safe_load(Path(__file__).with_name("domains.yaml").read_text(encoding="utf-8"))
    return {key:DomainDefinition.model_validate({"version":raw["version"],**value}) for key,value in raw["domains"].items()}


class PlatformContext(Contract):
    domain: Domain | None = None
    usage: ConversationContext = Field(default_factory=ConversationContext)
    sales: SalesContext = Field(default_factory=SalesContext)
    marketing: BusinessContext = Field(default_factory=BusinessContext)
    finance: BusinessContext = Field(default_factory=BusinessContext)

    @property
    def request(self): return getattr(self,self.domain or "usage").request


class PlatformAnswer(Contract):
    domain: Domain | None = None
    status: Literal["ok","clarification","unsupported","error"]
    provider: str
    model: str = ""
    fallback_reason: str | None = None
    message: str
    findings: list[str] = Field(default_factory=list)
    results: list[SkillResult | SalesResult | BusinessResult] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
    context: PlatformContext = Field(default_factory=PlatformContext)
    elapsed_ms: float
    tool_calls: int = 0
    knowledge: dict = Field(default_factory=dict)


def route_domain(question, context):
    text=question.lower()
    usage=bool(re.search(r"active users|\bmau\b|\bdau\b|activation|adoption|existing users|new users|cohorts?|registration|service usage",text))
    marketing=bool(re.search(r"\bmarketing\b|\bcampaigns?\b|\bimpressions\b|\bconversions?\b|\bclicks\b|click[ -]through|cost per click|\bctr\b|\bcpc\b",text))
    finance=bool(re.search(r"\bfinance\b|\bdepartments?\b|\bexpenses?\b|\bprofit\b|\bmargin\b|booked revenue|cost of goods|operating expense",text))
    sales=bool(re.search(r"\bsales\b|units sold|\borders\b|order value|\baov\b",text))
    choices=[name for name,found in (("usage",usage),("sales",sales),("marketing",marketing),("finance",finance)) if found]
    if len(choices)>1:return None,"Choose one domain per question: account usage, sales, marketing or finance. Cross-domain joins are not registered."
    if choices:return choices[0],""
    if re.search(r"\brevenue\b",text):return ("finance" if context.domain=="finance" else "sales"),""
    if context.domain: return context.domain,""
    # Existing documented decline/quality questions remain usage questions.
    if re.search(r"decline|activity data|which markets",text): return "usage",""
    return None,"Which domain and metric should I analyze: account usage, sales, marketing or finance?"


def business_findings(results):
    first=results[0];unit=first.definition['unit']
    def fmt(value):return "undefined" if value is None else f"${value:,.2f} USD" if unit=='usd' else f"{value:.2%}" if unit=='ratio' else f"{value:,.0f}"
    delta=f"{first.absolute_change*100:+.2f} pp" if unit=='ratio' and first.absolute_change is not None else fmt(first.absolute_change)
    relative=f"{first.percentage_change:+.2f}%" if first.percentage_change is not None else 'undefined'
    findings=[f"Observed {first.request.metric.replace('_',' ')}: {fmt(first.baseline)} → {fmt(first.current)}; change {delta} ({relative} relative)."]
    if not first.quality['complete']:findings.insert(0,'Provisional result: required coverage is incomplete.')
    for result in results:
        if result.records:
            ranked=sorted((r for r in result.records if r['change'] is not None),key=lambda r:abs(r['change']),reverse=True)
            if ranked:
                row=ranked[0];change=f"{row['change']*100:+.2f} pp" if unit=='ratio' else fmt(row['change'])
                findings.append(f"Largest observed group change: {row['group']} changed by {change}.")
            findings.append('Exclusive group amounts reconcile to the total.' if result.reconciliation.get('reconciled') else 'Ratios are not additive; totals use summed numerators and denominators.')
    findings.append('These synthetic observations and contributions do not establish a confirmed business cause.')
    return findings


def sales_findings(results):
    first=results[0]; money=first.request.metric in ("net_sales","avg_order_value")
    def fmt(value): return "undefined" if value is None else f"${value:,.2f} USD" if money else f"{value:,.0f}"
    relative=f"{first.percentage_change:+.2f}%" if first.percentage_change is not None else "undefined"
    findings=[f"Observed {first.request.metric.replace('_',' ')}: {fmt(first.baseline)} → {fmt(first.current)}; change {fmt(first.absolute_change)} ({relative} relative)."]
    if not first.quality["complete"]: findings.insert(0,"Provisional sales result: required coverage is incomplete.")
    for result in results:
        if result.records:
            ranked=sorted((r for r in result.records if r["change"] is not None),key=lambda r:abs(r["change"]),reverse=True)
            if ranked:
                row=ranked[0]
                findings.append(f"Largest observed group change: {row['group']} changed by {fmt(row['change'])}.")
            findings.append("Group changes reconcile to the total." if result.reconciliation.get("reconciled") else "Group populations overlap or the metric is a ratio; group changes cannot be summed.")
    findings.append("These are fictional sales observations and contributions; they do not establish a confirmed business cause.")
    return findings


class PlatformAgent:
    def __init__(self, usage_skills=None, sales_skills=None, settings=None, scope=AccessScope(), business_skills=None):
        self.usage_skills=usage_skills or SkillRegistry()
        self.sales_skills=sales_skills
        self.business_skills=business_skills or {}
        self.settings=settings or load_settings()
        self.scope=scope

    def run(self, question, context=None, mode=None, manager=None):
        started=time.perf_counter()
        if isinstance(context,ConversationContext): context=PlatformContext(domain="usage",usage=context)
        context=context or PlatformContext()
        mode=mode or ("demo" if self.settings.public_demo_enabled else self.settings.llm_provider)
        events=[]; domain=None; results=[]; knowledge={}; actual="deterministic demo" if mode=="demo" else mode
        model=""; fallback=None; owns_manager=False
        token=DEADLINE.set(started+self.settings.investigation_timeout)
        def event(index,status="complete",**facts):
            elapsed=round((time.perf_counter()-started)*1000,3)
            previous=events[-1]["elapsed_ms"] if events else 0
            events.append({"component_id":index,"stage":STAGES[index-1],"status":status,
                "elapsed_ms":elapsed,"duration_ms":round(elapsed-previous,3),**facts})
        def answer(status,message,**extras):
            while len(events)<7: event(len(events)+1,"not_executed",reason="Execution stopped after clarification, refusal, or error.")
            return PlatformAnswer(domain=domain,status=status,provider=actual,model=model,fallback_reason=fallback,
                message=message,results=results,trace=events,context=context,knowledge=knowledge,
                elapsed_ms=(time.perf_counter()-started)*1000,tool_calls=len(results),**extras)
        try:
            if not isinstance(question,str) or not question.strip() or len(question)>2000:
                event(1,"refused",reason="Question must contain 1–2000 characters.")
                return answer("unsupported","Enter a supported question of at most 2000 characters.")
            if re.search(r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}",question):
                event(1,"refused",reason="Credential-like content is not accepted in analytical questions.")
                return answer("unsupported","Remove credentials from the analytical question.")
            event(1,characters=len(question),execution_mode=mode)
            if self.settings.public_demo_enabled and mode!="demo": raise PermissionError("Public synthetic analytics cannot use LLM providers.")
            domain,message=route_domain(question,context)
            if domain is None:
                event(2,"clarification",reason=message)
                return answer("clarification",message)
            if domain not in self.scope.domains: raise PermissionError("Requested domain outside this account's approved scope.")
            if domain=="usage":
                parsed=parse_demo(question,context.usage)
                event(2,domain=domain,action=parsed.action,request=parsed.request.model_dump(mode="json") if parsed.request else None)
                if parsed.action!="execute" and mode=="demo":
                    return answer("clarification" if parsed.action=="clarify" else "unsupported",parsed.message)
                event(3,registry=domain_registry()[domain].model_dump(),skills=[t.skill for t in parsed.tasks])
                from analytics_agent.semantics import registry
                knowledge={"definitions":{key:value.model_dump() for key,value in registry().items()}}
                event(4,source="metrics.yaml",registered_metrics=list(knowledge["definitions"]))
                event(5,policy="Internal parameterized usage templates; SQL cannot be supplied by the model.")
                output=AnalyticsAgent(self.usage_skills,self.settings,self.scope).run(question,context.usage,mode,manager)
                actual,model,fallback=output.provider,output.model,output.fallback_reason
                results=output.results
                event(6,"complete" if output.status=="ok" else output.status,executed_skills=[r.skill for r in results],
                    query_evidence=[item.model_dump(mode="json") for r in results for item in r.evidence],execution_trace=output.trace)
                context=PlatformContext(domain="usage",usage=output.context,sales=SalesContext())
                event(7,"complete" if output.status=="ok" else "not_executed",result_count=len(results))
                return answer(output.status,output.message,findings=output.findings,followups=output.followups)
            is_sales=domain=="sales"
            domain_context=getattr(context,domain)
            plan=parse_sales(question,domain_context) if is_sales else parse_business(question,domain,domain_context)
            event(2,domain=domain,action=plan.action,request=plan.request.model_dump(mode="json") if plan.request else None,period_resolution=plan.message)
            if plan.action!="execute": return answer("clarification" if plan.action=="clarify" else "unsupported",plan.message or "Use a supported domain question.")
            skills=(self.sales_skills or SalesSkills()) if is_sales else (self.business_skills.get(domain) or BusinessSkills(domain))
            if callable(skills): skills=skills()
            engine=skills.engine
            if self.settings.public_demo_enabled:
                manifest=json.loads((engine.data_dir/"manifest.json").read_text(encoding="utf-8"))
                if engine.data_dir!=(PROJECT_ROOT/"data"/f"synthetic_{domain}").resolve() or manifest.get("is_synthetic") is not True or (not is_sales and manifest.get("domain")!=domain):
                    raise PermissionError("Public analytics requires the matching bundled fictional warehouse.")
            if domain_context.request: engine.authorize(domain_context.request,self.scope)
            count=2 if plan.operation=="investigation" else 1
            if count>min(self.settings.max_tool_calls,self.settings.investigation_depth): raise ValueError("Domain skill limit exceeded")
            engine.authorize(plan.request,self.scope)
            event(3,registry=domain_registry()[domain].model_dump(),operation=plan.operation,dimension=plan.dimension)
            knowledge,metadata_evidence=engine.knowledge(plan.request,self.scope)
            event(4,definition=knowledge["metric"],catalog=knowledge["catalog"],schemas=knowledge["schemas"],
                query_evidence=[r.model_dump(mode="json") for r in metadata_evidence])
            if mode!="demo":
                if mode not in ("ollama","openai"): raise ValueError("Unknown provider")
                if manager is None:
                    manager=manager_from_settings(self.settings,selected=mode,timeout=min(self.settings.llm_timeout,self.settings.investigation_timeout/2))
                    owns_manager=True
                manager.deadline=DEADLINE.get()
                plan_type=SalesPlan if is_sales else BusinessPlan
                tool_name="plan_"+domain
                tool={"type":"function","function":{"name":tool_name,"description":"Choose the approved synthetic domain request; never SQL or numerical findings.","parameters":plan_type.model_json_schema()}}
                reply=manager.chat([{"role":"system","content":f"Plan synthetic {domain} only. Dates April–September 2026; UTC half-open boundaries. Q3 uses Q2 baseline. Use the approved contract when provided. Never output SQL, permissions or numbers. Call {tool_name} once."},
                    {"role":"user","content":json.dumps({"question":question,"context":domain_context.model_dump(mode="json"),
                        "approved_contract":plan.model_dump(mode="json"),"retrieved_knowledge":knowledge,
                        "allowed_scope":self.scope.model_dump(mode="json")})}],tools=[tool])
                actual,model,fallback=manager.actual_provider,reply.model,manager.last_fallback_reason
                if len(reply.tool_calls)!=1 or reply.tool_calls[0].name!=tool_name: raise ValueError("Unapproved domain planning tool")
                proposed=plan_type.model_validate(reply.tool_calls[0].arguments)
                if proposed.action=="execute": skills.query_plan(proposed,self.scope)
                if proposed.action!="execute": raise ValueError("Model did not return the approved sales execution contract.")
                # The approved question contract controls semantics; model prose/numbers are ignored.
            queries=skills.query_plan(plan,self.scope)
            event(5,policy="Allowlisted parameterized SQL; no unrestricted model SQL",queries=[q.model_dump(mode="json") for q in queries])
            results=skills.execute(plan,self.scope,queries,knowledge)
            event(6,executed_skills=[r.skill for r in results],quality=results[0].quality,
                reconciliations=[r.reconciliation for r in results],query_evidence=[e.model_dump(mode="json") for e in results[0].evidence])
            findings=sales_findings(results) if is_sales else business_findings(results)
            summary=findings[0]
            if plan.message:
                findings.insert(0,plan.message)
                summary=plan.message+" "+summary
            context=PlatformContext(domain=domain,**{domain:SalesContext(request=plan.request) if is_sales else BusinessContext(request=plan.request)})
            event(7,result_count=len(results),finding_basis="Executed query values only",chart_rows=sum(len(r.trend)+len(r.records) for r in results))
            followups=["Which markets contributed to the change in net sales for the same periods?","Now compare only Orion One for the same periods.","Investigate net sales across products for the same periods."] if is_sales else (
                ["Which campaigns contributed to the change in marketing conversions for the same periods?","Now compare only Campaign Aurora for the same periods.","Investigate marketing spend across channels for the same periods."] if domain=='marketing' else
                ["Which departments contributed to the change in finance expenses for the same periods?","Now compare only Department Boreal for the same periods.","Investigate finance profit across categories for the same periods."])
            return answer("ok",summary,findings=findings,followups=followups)
        except (PermissionError,ValueError,TimeoutError,ProviderError,FileNotFoundError) as error:
            results=[]
            if manager is not None: fallback=manager.last_fallback_reason
            event(min(len(events)+1,7),"error",error_type=type(error).__name__)
            message=str(error) if isinstance(error,(PermissionError,TimeoutError,ProviderError)) else "Analytical configuration or data validation failed; results withheld."
            return answer("error",message)
        except Exception as error:
            results=[]
            event(min(len(events)+1,7),"error",error_type=type(error).__name__)
            return answer("error","Analytical execution failed; results withheld. Check source validation and execution limits.")
        finally:
            DEADLINE.reset(token)
            if owns_manager and manager is not None: manager.close()
