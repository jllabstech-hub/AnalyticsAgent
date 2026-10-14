from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, ConfigDict
import yaml
from analytics_agent.models import Metric


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric_id: Metric
    version: str
    business_meaning: str
    calculation_method: str
    source_datasets: list[str]
    required_joins: list[str]
    timezone: str
    aggregation_grain: str
    supported_dimensions: list[str]
    numerator: str
    denominator: str | None
    owner: str
    data_quality_requirements: list[str]


@lru_cache(maxsize=1)
def registry():
    raw = yaml.safe_load(Path(__file__).with_name("metrics.yaml").read_text(encoding="utf-8"))
    definitions = {name: MetricDefinition.model_validate(value) for name, value in raw["metrics"].items()}
    if any(name != definition.metric_id for name, definition in definitions.items()):
        raise ValueError("Semantic registry ID mismatch.")
    return definitions


def resolve(metric):
    if metric not in registry():
        raise ValueError("Unsupported metric.")
    return registry()[metric]
