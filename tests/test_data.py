import json
from pathlib import Path
from scripts.validate_data import validate

ROOT = Path(__file__).resolve().parents[1]


def test_generated_warehouse_integrity():
    report = validate(ROOT / "data" / "synthetic")
    assert report["unique_users"] == 100_000
    assert len(report["market_distribution"]) == 5
    assert len(report["monthly_active_users"]) == 3
    assert report["incomplete_september_days"] == 23


def test_independent_references_and_injected_patterns():
    references = json.loads((ROOT / "tests" / "fixtures" / "reference_answers.json").read_text())
    assert len(references) >= 30
    scopes = {c["id"]: c for c in references}
    assert scopes["mau-1"]["current"] < scopes["mau-1"]["baseline"]
    assert scopes["mau-2"]["current"] > scopes["mau-2"]["baseline"]
