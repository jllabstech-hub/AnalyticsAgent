"""Typed Marketing/Finance contracts; no SQL, source paths or grants in tools."""
from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from analytics_agent.models import Contract, Market, QueryEvidence

BusinessDomain = Literal["marketing", "finance"]
METRICS = {
    "marketing": ("impressions", "clicks", "conversions", "marketing_spend", "click_through_rate", "conversion_rate", "cost_per_click"),
    "finance": ("finance_revenue", "expenses", "profit", "profit_margin"),
}
ENTITIES = {"marketing": ("Campaign Aurora", "Campaign Boreal", "Campaign Cinder", "Campaign Delta"),
            "finance": ("Department Aurora", "Department Boreal", "Department Cinder")}
CHANNELS = ("Channel Search", "Channel Social", "Channel Email")
CATEGORIES = ("Revenue", "Cost of Goods", "Operating Expense")
DIMENSIONS = {"marketing": ("market", "campaign", "channel"), "finance": ("market", "department", "category")}


class BusinessPeriod(Contract):
    start: date
    end: date

    @model_validator(mode="after")
    def valid_range(self):
        if not date(2026, 4, 1) <= self.start < self.end <= date(2026, 10, 1):
            raise ValueError("Use April–September 2026 UTC periods with exclusive end dates.")
        return self


class BusinessRequest(Contract):
    domain: BusinessDomain
    metric: str
    baseline: BusinessPeriod = Field(default_factory=lambda: BusinessPeriod(start="2026-04-01", end="2026-07-01"))
    current: BusinessPeriod = Field(default_factory=lambda: BusinessPeriod(start="2026-07-01", end="2026-10-01"))
    market: Market | None = None
    entity: str | None = None
    channel: Literal["Channel Search", "Channel Social", "Channel Email"] | None = None
    category: Literal["Revenue", "Cost of Goods", "Operating Expense"] | None = None
    scenario: Literal["primary", "incomplete"] = "primary"

    @model_validator(mode="after")
    def approved_population(self):
        if self.metric not in METRICS[self.domain]: raise ValueError("Metric outside registered domain.")
        if self.entity is not None and self.entity not in ENTITIES[self.domain]: raise ValueError("Unregistered domain entity.")
        if self.domain == "marketing" and self.category is not None: raise ValueError("Marketing does not support finance categories.")
        if self.domain == "finance" and self.channel is not None: raise ValueError("Finance does not support marketing channels.")
        return self


class BusinessPlan(Contract):
    action: Literal["execute", "clarify", "unsupported"]
    request: BusinessRequest | None = None
    operation: Literal["comparison", "contribution", "investigation"] = "comparison"
    dimension: Literal["market", "campaign", "channel", "department", "category"] = "market"
    message: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def approved_execution(self):
        if self.action == "execute" and self.request is None: raise ValueError("Execution requires an approved request.")
        if self.request and self.dimension not in DIMENSIONS[self.request.domain]: raise ValueError("Unsupported domain dimension.")
        return self


class BusinessContext(Contract):
    request: BusinessRequest | None = None


class BusinessResult(Contract):
    skill: Literal["M1", "M2", "F1", "F2"]
    skill_version: str = "1.0"
    metric_version: str = "1.0"
    request: BusinessRequest
    definition: dict
    baseline: float | None
    current: float | None
    absolute_change: float | None
    percentage_change: float | None
    records: list[dict] = Field(default_factory=list)
    trend: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    quality: dict = Field(default_factory=dict)
    evidence: list[QueryEvidence] = Field(default_factory=list)
    reconciliation: dict = Field(default_factory=dict)
    queries: list[dict] = Field(default_factory=list)
    duration_ms: float
