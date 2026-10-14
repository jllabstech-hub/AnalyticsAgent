"""Validated public contracts; tool arguments cannot carry SQL or permissions."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Metric = Literal["dau", "mau", "new_users", "active_existing_users", "activation_rate", "service_adoption_rate"]
Market = Literal["Market A", "Market B", "Market C", "Market D", "Market E"]
Service = Literal["Service Alpha", "Service Beta", "Service Gamma"]
Device = Literal["Orion One", "Orion Plus", "Nova Mini", "Nova Fold"]
Dimension = Literal["market", "device_model", "service"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Period(Contract):
    start: date
    end: date

    @model_validator(mode="after")
    def validate_range(self):
        if not date(2026, 7, 1) <= self.start < self.end <= date(2026, 10, 1):
            raise ValueError("Use a nonempty half-open period within July–September 2026.")
        return self


class AnalyticsRequest(Contract):
    metric: Metric = "mau"
    baseline: Period = Field(default_factory=lambda: Period(start="2026-08-01", end="2026-09-01"))
    current: Period = Field(default_factory=lambda: Period(start="2026-09-01", end="2026-10-01"))
    market: Market | None = None
    service: Service | None = None
    device_model: Device | None = None
    scenario: Literal["primary", "incomplete"] = "primary"


class AccessScope(Contract):
    # Existing private grants stay usage-only until sales is explicitly approved.
    domains: tuple[Literal["usage", "sales"], ...] = ("usage",)
    markets: tuple[Market, ...] = ("Market A", "Market B", "Market C", "Market D", "Market E")
    services: tuple[Service, ...] = ("Service Alpha", "Service Beta", "Service Gamma")
    skills: tuple[Literal["K1", "K2", "K3"], ...] = ("K1", "K2", "K3")


class MetricValue(Contract):
    value: float | None
    numerator: float
    denominator: float | None = None
    group: str = "All"


class QueryEvidence(Contract):
    query_id: str
    template: str
    duration_ms: float
    rows: int
    parameters: dict
    sources: list[str]
    query_version: str = "1.1"
    cache_hit: bool = False
