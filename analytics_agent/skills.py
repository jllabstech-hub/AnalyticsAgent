"""Deterministic skills: computed evidence, no LLM or evaluation-fixture imports."""
import math
import time
from typing import Literal
from pydantic import Field
from analytics_agent.engine import Engine
from analytics_agent.models import AccessScope, AnalyticsRequest, Contract, Dimension, Period, QueryEvidence
from analytics_agent.semantics import resolve


class ToolArguments(Contract):
    request: AnalyticsRequest
    dimension: Dimension = "market"
    cohort: Literal["new_existing", "registration", "membership"] = "new_existing"


class SkillResult(Contract):
    skill: Literal["K1", "K2", "K3"]
    skill_version: str = "1.1"
    metric_version: str
    request: AnalyticsRequest
    definition: dict
    baseline: float | None
    current: float | None
    absolute_change: float | None
    percentage_change: float | None
    records: list[dict] = Field(default_factory=list)
    trend: list[dict] = Field(default_factory=list)
    trend_metric: str = "Daily Active Users"
    warnings: list[str] = Field(default_factory=list)
    quality: dict = Field(default_factory=dict)
    evidence: list[QueryEvidence] = Field(default_factory=list)
    reconciliation: dict = Field(default_factory=dict)
    duration_ms: float


def changes(baseline, current):
    difference = current - baseline if current is not None and baseline is not None else None
    percent = difference / baseline * 100 if difference is not None and baseline else None
    return difference, percent


def validate_values(values):
    for item in values:
        if item.value is not None and not math.isfinite(item.value):
            raise ValueError("Non-finite analytical result.")
        if item.denominator is not None and (item.denominator < 0 or item.numerator < 0 or item.numerator > item.denominator):
            raise ValueError("Invalid metric denominator or population.")


class SkillRegistry:
    names = {"K1": "Metric Comparison", "K2": "Contribution Breakdown", "K3": "Cohort Comparison"}

    def __init__(self, engine=None):
        self.engine = engine or Engine()

    def execute(self, skill, arguments: ToolArguments, scope=AccessScope()):
        if skill not in self.names or skill not in scope.skills:
            raise PermissionError("Skill outside approved allowlist.")
        started = time.perf_counter()
        request = arguments.request
        self.engine.authorize(request, scope)
        definition = resolve(request.metric)
        if arguments.dimension not in definition.supported_dimensions:
            raise ValueError("Unsupported dimension for this metric.")
        baseline, baseline_evidence = self.engine.metric(request, request.baseline, scope)
        current, current_evidence = self.engine.metric(request, request.current, scope)
        validate_values(baseline+current)
        base, now = baseline[0].value, current[0].value
        evidence = [baseline_evidence, current_evidence]
        warnings = []
        coverage, event_stats, quality_evidence = self.engine.quality(request, scope)
        evidence.extend(quality_evidence)
        complete = True
        for source in definition.source_datasets:
            for period in (request.baseline,request.current):
                cursor = period.start
                spans = sorted((r for r in coverage if r["dataset"] == source),key=lambda r:r["period_start"])
                for span in spans:
                    start, end = span["period_start"].date(), min(span["period_end"],span["available_through"]).date()
                    if start <= cursor < end: cursor = end
                if cursor < period.end:
                    complete = False
                    warnings.append(f"Missing or incomplete coverage metadata for {source}; the comparison is provisional.")
        if any(not row["complete"] for row in coverage):
            complete = False
            warnings.append("Incomplete reporting period: comparison is provisional and unsuitable for causal interpretation.")
        if event_stats["raw_rows"] > event_stats["unique_events"]:
            warnings.append(f"Removed {event_stats['raw_rows'] - event_stats['unique_events']:,} duplicate event rows before counting users.")
        if event_stats["late_events"]:
            warnings.append(f"{event_stats['late_events']:,} unique events arrived more than 24 hours late; the primary snapshot includes them.")
        for row in coverage:
            if (row["snapshot_as_of"] - row["loaded_at"]).days > 2:
                warnings.append(f"Stale snapshot for {row['dataset']}.")
        if any(v.denominator == 0 for v in baseline + current):
            warnings.append("Zero denominator: rate is undefined, not zero.")
        records, trend, reconciliation = [], [], {}
        if skill == "K1":
            span = Period(start=min(request.baseline.start, request.current.start), end=max(request.baseline.end, request.current.end))
            trend, trend_evidence = self.engine.trend(request, span, scope)
            evidence.append(trend_evidence)
        else:
            grouping = arguments.dimension if skill == "K2" else arguments.cohort
            left, left_evidence = self.engine.metric(request, request.baseline, scope, grouping)
            right, right_evidence = self.engine.metric(request, request.current, scope, grouping)
            validate_values(left+right)
            evidence.extend([left_evidence, right_evidence])
            lmap, rmap = {x.group: x for x in left}, {x.group: x for x in right}
            is_rate = request.metric.endswith("rate")
            for group in sorted(set(lmap) | set(rmap)):
                b = lmap[group].value if group in lmap else (None if is_rate else 0.)
                c = rmap[group].value if group in rmap else (None if is_rate else 0.)
                delta, percent = changes(b, c)
                records.append({"group": group, "baseline": b, "current": c, "change": delta, "percentage_change": percent})
            exclusive = not is_rate and base is not None and now is not None and math.isclose(sum(x["baseline"] for x in records), base, abs_tol=1e-7) and math.isclose(sum(x["current"] for x in records), now, abs_tol=1e-7)
            reconciliation = {"additive": not is_rate, "mutually_exclusive": exclusive, "reconciled": exclusive,
                "sum_group_changes": sum(x["change"] for x in records if x["change"] is not None) if exclusive else None,
                "total_change": changes(base, now)[0]}
            if not exclusive:
                warnings.append("Group counts overlap or the metric is a ratio; group changes must not be added to explain the total.")
            if skill == "K3" and grouping == "new_existing":
                warnings.append("New/existing cohorts are defined separately at each period start; this is not a fixed-cohort retention measure.")
        delta, percent = changes(base, now)
        for record in records:
            record["contribution_pct"] = record["change"] / delta * 100 if reconciliation.get("reconciled") and delta else None
        return SkillResult(skill=skill, metric_version=definition.version, request=request,
            definition=definition.model_dump(), baseline=base, current=now, absolute_change=delta,
            percentage_change=percent, records=records, trend=trend, warnings=list(dict.fromkeys(warnings)),
            quality={"coverage": coverage, "events": event_stats, "complete":complete,"freshness_basis": "Historical synthetic snapshot 2026-10-05"},
            evidence=evidence, reconciliation=reconciliation, duration_ms=round((time.perf_counter()-started)*1000,3))
