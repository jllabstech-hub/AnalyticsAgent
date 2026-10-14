"""Sales contracts contain approved filters and operations, never SQL or grants."""
from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from analytics_agent.models import Contract, Market, Device, QueryEvidence

SalesMetric = Literal["net_sales", "units_sold", "orders", "avg_order_value"]
SalesDimension = Literal["market", "product", "channel"]
Channel = Literal["Fictional Web", "Fictional Shops", "Fictional Partners"]


class SalesPeriod(Contract):
    start: date
    end: date

    @model_validator(mode="after")
    def valid_range(self):
        if not date(2026, 4, 1) <= self.start < self.end <= date(2026, 10, 1):
            raise ValueError("Sales periods must be within April–September 2026; end dates are exclusive.")
        return self


class SalesRequest(Contract):
    metric: SalesMetric = "net_sales"
    baseline: SalesPeriod = Field(default_factory=lambda: SalesPeriod(start="2026-04-01", end="2026-07-01"))
    current: SalesPeriod = Field(default_factory=lambda: SalesPeriod(start="2026-07-01", end="2026-10-01"))
    market: Market | None = None
    product: Device | None = None
    channel: Channel | None = None
    scenario: Literal["primary", "incomplete"] = "primary"


class SalesPlan(Contract):
    action: Literal["execute", "clarify", "unsupported"]
    request: SalesRequest | None = None
    operation: Literal["comparison", "contribution", "investigation"] = "comparison"
    dimension: SalesDimension = "market"
    message: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def execution_requires_request(self):
        if self.action == "execute" and self.request is None:
            raise ValueError("Execution requires a validated sales request.")
        return self


class SalesContext(Contract):
    request: SalesRequest | None = None


class SalesResult(Contract):
    skill: Literal["S1", "S2"]
    skill_version: str = "1.0"
    metric_version: str = "1.0"
    request: SalesRequest
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
