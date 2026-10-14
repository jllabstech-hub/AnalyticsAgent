import json
from scripts.generate_sales_data import generate
from scripts.sales_reference import load


def test_sales_generation_is_reproducible_and_valid(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    first = generate(one, orders=250)
    second = generate(two, orders=250)
    a, report = load(one)
    b, _ = load(two)
    assert first == second and a.equals(b)
    assert report["unique_orders"] == 250 and report["unique_sales_lines"] == 500
    assert report["duplicate_rows"] == 5 and report["join_cardinality"] == "pass"
    assert json.loads((one / "manifest.json").read_text())["is_synthetic"] is True


def test_bundled_sales_warehouse_and_reference_grain():
    from analytics_agent.config import PROJECT_ROOT
    data, report = load()
    assert len(data) == 50000 and report["unique_orders"] == 25000
    assert report["duplicate_rows"] == 500 and len(report["monthly_net_cents"]) == 6
    assert len(report["market_distribution"]) == 5
    cases = json.loads((PROJECT_ROOT / "tests/fixtures/sales_reference_answers.json").read_text())
    assert len(cases) == 40
