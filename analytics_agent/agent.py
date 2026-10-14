"""Bounded plan/execute/explain workflow with computation-only numerical truth."""
import json
import logging
import re
import time
from typing import Literal
from pydantic import Field, field_validator, model_validator
from analytics_agent.config import load_settings
from analytics_agent.engine import DEADLINE, Engine
from analytics_agent.models import AccessScope, AnalyticsRequest, Contract, Period
from analytics_agent.providers import ProviderError, manager_from_settings
from analytics_agent.skills import SkillRegistry, SkillResult, ToolArguments
from analytics_agent.semantics import registry

DEMOS = ["Compare August and September active users.", "Which markets contributed most to the decline?",
         "Investigate the September decline across markets and cohorts.", "Can we trust the September activity data?",
         "Now compare only Market A for the same periods."]


class Task(Contract):
    skill: Literal["K1", "K2", "K3"]
    dimension: Literal["market", "service", "device_model"] = "market"
    cohort: Literal["new_existing", "registration", "membership"] = "new_existing"


class Plan(Contract):
    action: Literal["execute", "clarify", "unsupported"]
    request: AnalyticsRequest | None = None
    tasks: list[Task] = Field(default_factory=list, max_length=6)
    message: str = Field(default="", max_length=1000)
    intent: Literal["comparison", "contribution", "investigation", "quality", "cohort"] = "comparison"

    @field_validator("tasks")
    @classmethod
    def unique_tasks(cls, tasks):
        # All tasks share one request; repeating an effective calculation adds no evidence.
        unique, seen = [], set()
        for task in tasks:
            key = (task.skill, task.dimension if task.skill == "K2" else task.cohort if task.skill == "K3" else None)
            if key not in seen:
                unique.append(task)
                seen.add(key)
        return unique

    @model_validator(mode="after")
    def valid_execution(self):
        if self.action == "execute" and (self.request is None or not self.tasks):
            raise ValueError("Executable plans require a request and at least one registered skill.")
        return self


class ConversationContext(Contract):
    request: AnalyticsRequest | None = None


class ObservationSelection(Contract):
    observation_ids: list[str] = Field(max_length=32)


class AgentAnswer(Contract):
    status: Literal["ok", "clarification", "unsupported", "error"]
    provider: str
    model: str = ""
    fallback_reason: str | None = None
    message: str
    findings: list[str] = Field(default_factory=list)
    results: list[SkillResult] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
    context: ConversationContext = Field(default_factory=ConversationContext)
    elapsed_ms: float
    tool_calls: int = 0


def parse_demo(question, context=ConversationContext()):
    text = question.strip().lower()
    if len(text) > 2000:
        return Plan(action="unsupported", message="Question exceeds the supported size.")
    if re.search(r"\b(revenue|sales|real data|password|delete|drop table|sql|employee|root cause confirmed|forecast|predict)\b", text):
        return Plan(action="unsupported", message="This prototype supports fictional account usage analytics only. That data or operation is unsupported.")
    if re.search(r"\b(202[0-57-9]|20[013-9]\d|october|november|december|january|february|march|april|may|june)\b", text):
        return Plan(action="unsupported", message="Available reporting dates are July–September 2026 only.")
    if not re.search(r"\b(compare|investigate|why|which|trust|show|now)\b", text):
        return Plan(action="clarify", message="Choose a documented comparison or investigation, with a metric and reporting months.")
    if re.search(r"\b(?:july|august|september)\s+\d|\b\d{4}-\d{2}-\d{2}\b",text):
        return Plan(action="clarify",message="Deterministic mode accepts whole-month comparisons. Use two month names; day-level requests require a validated LLM plan.")
    # Unknown filter text must not silently become an unfiltered population.
    for clause in re.findall(r"\b(?:for|on)\s+(.+)",text):
        residual = clause.rstrip(".?!")
        for known in ["the same periods","same periods","in the incomplete scenario","in the primary scenario","incomplete scenario","primary scenario","all users","all markets","all services","all devices"] + [f"market {c}" for c in "abcde"] + [f"service {c}" for c in ("alpha","beta","gamma")] + ["orion one","orion plus","nova mini","nova fold"]:
            residual = re.sub(r"\b"+re.escape(known)+r"\b","",residual)
        residual = re.sub(r"\b(?:and|only|for|the)\b|[,;]","",residual).strip()
        if residual:
            return Plan(action="unsupported",message="A requested filter is unsupported in deterministic mode. Use an approved market, service or device name.")
    cohort_comparison = bool(re.search(r"\bnew(?: users)?\s+(?:versus|vs\.?|and)\s+existing(?: users)?\b",text))
    metrics = [("activation", "activation_rate"), ("adoption", "service_adoption_rate"),
        ("existing users", "active_existing_users"), ("new users", "new_users"), ("dau", "dau"), ("daily active", "dau"), ("mau", "mau"), ("active users", "mau")]
    metric = next((value for phrase, value in metrics if phrase in text), None)
    if cohort_comparison: metric = "mau"
    previous = context.request
    months = re.findall(r"\b(july|august|september)\b", text)
    if metric is None:
        if previous:
            # Context fills analytic filters; it cannot turn an unknown subject into MAU.
            if not re.search(r"\b(market|markets|device|devices|service|services|cohort|cohorts|registration|membership|decline|activity)\b|same periods",text):
                return Plan(action="unsupported",message="This follow-up requests unsupported data. Use the documented account-usage questions.")
            metric = previous.metric
        elif "decline" in text or "activity data" in text:
            metric = "mau"
        else:
            return Plan(action="clarify", message="Which metric should I compare: MAU, DAU, new users, existing users, activation rate, or adoption rate?")
    if not months and not previous:
        return Plan(action="clarify", message="Which baseline and comparison months should I use within July–September 2026?")
    data = previous.model_dump(mode="json") if previous else AnalyticsRequest().model_dump(mode="json")
    data["metric"] = metric
    if months:
        indices = {"july":7,"august":8,"september":9}
        chosen = [indices[m] for m in dict.fromkeys(months)]
        if len(chosen) == 1:
            if chosen[0] == 7:
                return Plan(action="clarify", message="July is the earliest month. Specify a supported baseline and comparison month.")
            chosen = [chosen[0]-1, chosen[0]]
        if len(chosen) != 2:
            return Plan(action="clarify", message="Specify two comparison months.")
        data["baseline"] = {"start":f"2026-{chosen[0]:02}-01", "end":f"2026-{chosen[0]+1:02}-01"}
        data["current"] = {"start":f"2026-{chosen[1]:02}-01", "end":f"2026-{chosen[1]+1:02}-01"}
    for pattern, key, choices in [(r"\bmarket\s+([a-z][\w-]*)\b", "market", {c.lower():f"Market {c}" for c in "ABCDE"}),
            (r"\bservice\s+([a-z][\w-]*)\b", "service", {s:f"Service {s.title()}" for s in ["alpha","beta","gamma"]})]:
        matches = re.findall(pattern,text)
        if key == "service": matches = [m for m in matches if m not in ("adoption","categories","groups")]
        if len(set(matches)) > 1:
            return Plan(action="clarify",message="Use one group filter at a time, or ask for a group breakdown.")
        if matches:
            if matches[0] not in choices:
                return Plan(action="unsupported", message="Requested group is not in the approved synthetic warehouse.")
            data[key] = choices[matches[0]]
    for device in ("Orion One","Orion Plus","Nova Mini","Nova Fold"):
        if device.lower() in text:
            data["device_model"] = device
    if "all markets" in text:
        data["market"] = None
    if "all services" in text:
        data["service"] = None
    if "all devices" in text:
        data["device_model"] = None
    if "incomplete" in text:
        data["scenario"] = "incomplete"
    if "primary" in text:
        data["scenario"] = "primary"
    request = AnalyticsRequest.model_validate(data)
    dimension = "market" if "markets" in text else "device_model" if "device" in text else "service" if "services" in text or "categories" in text else "market"
    if "investigate" in text or "why" in text:
        tasks, intent = [Task(skill="K1"), Task(skill="K2",dimension=dimension), Task(skill="K3")], "investigation"
    elif "contribut" in text or "which markets" in text:
        tasks, intent = [Task(skill="K2",dimension=dimension)], "contribution"
    elif cohort_comparison or "cohort" in text or "registration" in text or "membership" in text:
        cohort = "registration" if "registration" in text else "membership" if "membership" in text else "new_existing"
        tasks, intent = [Task(skill="K3",cohort=cohort)], "cohort"
    else:
        tasks, intent = [Task(skill="K1")], "quality" if "trust" in text else "comparison"
    return Plan(action="execute", request=request, tasks=tasks, intent=intent)


def computed_findings(results, intent):
    facts = {}
    first = results[0]
    def formatted(value):
        if value is None:
            return "undefined"
        return f"{value:.2%}" if first.request.metric.endswith("rate") else f"{value:,.2f}".rstrip("0").rstrip(".")
    def delta(value):
        return f"{value*100:+.2f} pp" if value is not None and first.request.metric.endswith("rate") else formatted(value)
    facts["change"] = f"Observed {first.request.metric.upper()}: {formatted(first.baseline)} → {formatted(first.current)}; change {delta(first.absolute_change)} ({first.percentage_change:+.2f}% relative)." if first.percentage_change is not None else f"Observed {first.request.metric.upper()}: {formatted(first.baseline)} → {formatted(first.current)}; relative change is undefined."
    for result in results:
        if result.records:
            ranked = sorted((r for r in result.records if r["change"] is not None), key=lambda r: r["change"])
            if ranked:
                row = ranked[0]
                facts[f"{result.skill}_low"] = f"Observed group change: {row['group']} changed by {delta(row['change'])}. This is an observed contribution, not a confirmed cause." if result.reconciliation.get("reconciled") else f"Observed group change: {row['group']} changed by {delta(row['change'])}. Overlapping groups or ratios cannot be summed as contributions."
                largest = ranked[-1]
                facts[f"{result.skill}_high"] = f"{largest['group']} changed by {delta(largest['change'])}; examine this alongside declining groups."
                if result.skill == "K3" and row["change"] < 0:
                    facts["hypothesis"] = f"Hypothesis for follow-up: reduced participation in {row['group']} users may be associated with the overall change. These data do not establish why engagement changed."
    if intent == "quality":
        stats = first.quality["events"]
        facts["quality"] = f"Quality checks: {stats['raw_rows']:,} event rows, {stats['raw_rows']-stats['unique_events']:,} duplicate rows removed, {stats['late_events']:,} late unique events. Join cardinality passed."
    if not first.quality.get("complete",True):
        facts["change"] = "Provisional comparison. " + facts["change"]
        facts["completeness"] = "Provisional comparison: required reporting coverage is incomplete or unverified. Missing chart days are gaps, not zero activity."
    facts["limits"] = "These synthetic data show changes and associations. Causal explanations remain hypotheses; confirmed root cause requires additional evidence."
    return facts


class AnalyticsAgent:
    def __init__(self, skills=None, settings=None, scope=AccessScope()):
        self.settings = settings or load_settings()
        self.skills = skills or SkillRegistry(Engine(result_limit=self.settings.result_limit))
        self.scope = scope

    def run(self, question, context=ConversationContext(), mode=None, manager=None):
        started = time.perf_counter()
        mode = mode or ("demo" if self.settings.public_demo_enabled else self.settings.llm_provider)
        provider, model, fallback = "deterministic demo" if mode == "demo" else mode, "", None
        trace = [{"stage":"Understanding", "status":"complete"}]
        results = []
        owns_manager = manager is None and mode != "demo"
        token = DEADLINE.set(started + self.settings.investigation_timeout)
        try:
            if self.settings.public_demo_enabled and mode != "demo":
                raise PermissionError("Only deterministic analytics is allowed in the public synthetic demo.")
            if len(question) > 2000:
                raise ValueError("Question exceeds supported size.")
            if context.request:
                self.skills.engine.authorize(context.request, self.scope)
            if mode == "demo":
                plan = parse_demo(question, context)
            else:
                if mode not in ("ollama", "openai"):
                    raise ValueError("Select an available provider or explicit deterministic demo mode.")
                if manager is None:
                    manager = manager_from_settings(self.settings, selected=mode, timeout=min(self.settings.llm_timeout,self.settings.investigation_timeout/2))
                manager.deadline = DEADLINE.get()
                approved = parse_demo(question, context)
                prompt = {"question":question, "context":context.model_dump(mode="json"), "allowed_scope":self.scope.model_dump(mode="json"),
                    "metrics":{name:{"meaning":definition.business_meaning,"grain":definition.aggregation_grain,"dimensions":definition.supported_dimensions} for name,definition in registry().items()},
                    "skills":SkillRegistry.names}
                if approved.action == "execute":
                    prompt["approved_question_contract"] = approved.model_dump(mode="json")
                system = "Plan fictional usage analysis only. Available dates July–September 2026 UTC. Active users means MAU. Period ends are exclusive: whole months end on the first day of the next month. September decline uses August baseline. Ask clarification for missing metric/period. Follow an approved_question_contract when supplied. Only registered K1/K2/K3 skills. Simple comparisons use exactly K1; contributions use K2; explicit cohort comparisons use K3; investigations use K1,K2,K3; data quality uses K1. Never repeat an identical task. Never request SQL, credentials, or arbitrary code. Call plan_investigation exactly once; no numerical findings."
                tools = [{"type":"function", "function":{"name":"plan_investigation", "description":"Return a validated investigation or clarification plan.", "parameters":Plan.model_json_schema()}}]
                reply = manager.chat([{"role":"system","content":system},{"role":"user","content":json.dumps(prompt)}], tools=tools)
                provider, model, fallback = manager.actual_provider, reply.model, manager.last_fallback_reason
                if len(reply.tool_calls) != 1 or reply.tool_calls[0].name != "plan_investigation":
                    raise ValueError("Model must call the approved planning tool exactly once.")
                plan = Plan.model_validate(reply.tool_calls[0].arguments)
                if plan.action == "execute" and approved.action == "execute":
                    # A model cannot alter recognized question semantics or hide denied scope.
                    self.skills.engine.authorize(plan.request, self.scope)
                    if any(task.skill not in self.scope.skills for task in plan.tasks):
                        raise PermissionError("Plan contains a skill outside the authorized allowlist.")
                    if (plan.request, plan.tasks, plan.intent) != (approved.request, approved.tasks, approved.intent):
                        trace.append({"stage":"Understanding", "status":"approved question semantics applied"})
                    plan = approved
            if plan.action != "execute":
                # Model prose is used only for clarification/refusal, never analytical answers.
                message = plan.message if mode == "demo" else ("Please specify a supported usage metric and two reporting months." if plan.action == "clarify" else "This question requires unsupported data or analytical operations.")
                return AgentAnswer(status="clarification" if plan.action == "clarify" else "unsupported", provider=provider, model=model, fallback_reason=fallback, message=message or "Please specify a supported metric and periods.", trace=trace, context=context, elapsed_ms=(time.perf_counter()-started)*1000)
            self.skills.engine.authorize(plan.request, self.scope)
            if len(plan.tasks) > min(self.settings.max_tool_calls, self.settings.investigation_depth):
                raise ValueError("Plan exceeds the configured tool-call or depth limit.")
            if any(task.skill not in self.scope.skills for task in plan.tasks):
                raise PermissionError("Plan contains a skill outside the authorized allowlist.")
            trace.append({"stage":"Skill Selection", "status":"complete", "skills":[t.skill for t in plan.tasks]})
            for task in plan.tasks:
                if time.perf_counter() >= DEADLINE.get():
                    raise TimeoutError("Investigation deadline exceeded.")
                result = self.skills.execute(task.skill, ToolArguments(request=plan.request, dimension=task.dimension, cohort=task.cohort), self.scope)
                if len(result.records) + len(result.trend) > self.settings.result_limit:
                    raise ValueError("Analytical result exceeds the configured row limit.")
                results.append(result)
                trace.append({"stage":"Query Execution", "skill":task.skill, "status":"complete", "duration_ms":result.duration_ms})
            trace.append({"stage":"Validation", "status":"complete"})
            facts = computed_findings(results, plan.intent)
            findings = list(facts.values())
            # The model may order verified observations; it cannot supply numerical prose.
            if manager is not None and mode != "demo" and DEADLINE.get()-time.perf_counter() > self.settings.llm_timeout*2:
                schema = {"type":"object", "properties":{"observation_ids":{"type":"array","items":{"type":"string","enum":list(facts)}}}, "required":["observation_ids"], "additionalProperties":False}
                try:
                    explanation = manager.chat([{"role":"system","content":"Explain the computed result by selecting relevant observation_ids in order. Use only the supplied evidence. Do not invent new facts."}, {"role":"user","content":json.dumps(facts)}], schema=schema)
                    selected = ObservationSelection.model_validate_json(explanation.content).observation_ids
                    if selected and set(selected).issubset(facts):
                        findings = [facts[x] for x in dict.fromkeys(["change"]+selected)]
                        if "completeness" in facts and facts["completeness"] not in findings: findings.append(facts["completeness"])
                        if facts["limits"] not in findings:
                            findings.append(facts["limits"])
                    provider, model, fallback = manager.actual_provider, explanation.model, manager.last_fallback_reason
                except (ProviderError, ValueError, TypeError):
                    trace.append({"stage":"Findings", "status":"computed explanation used"})
            trace.append({"stage":"Findings", "status":"complete"})
            return AgentAnswer(status="ok", provider=provider, model=model, fallback_reason=fallback,
                message=findings[0], findings=findings, results=results,
                followups=["Investigate the change across markets and cohorts for the same periods.", f"Now compare only {self.scope.markets[0]} for the same periods.", "Now compare only Nova Mini for the same periods."],
                trace=trace, context=ConversationContext(request=plan.request), elapsed_ms=(time.perf_counter()-started)*1000, tool_calls=len(results))
        except (PermissionError, ValueError, TimeoutError, ProviderError) as error:
            if manager is not None and mode != "demo": fallback = manager.last_fallback_reason
            return AgentAnswer(status="error",provider=provider,model=model,fallback_reason=fallback,
                message=str(error) if isinstance(error,(PermissionError,TimeoutError,ProviderError)) else "Invalid analytical plan or unsupported parameters. Please use a supported question.", trace=trace,context=context,elapsed_ms=(time.perf_counter()-started)*1000,tool_calls=len(results))
        except Exception as error:
            logging.getLogger(__name__).warning("Analytical execution failed: %s",type(error).__name__)
            return AgentAnswer(status="error",provider=provider,message="Analytical execution failed; results have been withheld. Check dataset validation and execution limits.",trace=trace,context=context,elapsed_ms=(time.perf_counter()-started)*1000,tool_calls=len(results))
        finally:
            DEADLINE.reset(token)
            if owns_manager and manager is not None: manager.close()
