import json
from pathlib import Path
import pytest
from scripts.run_demos import run_demos


@pytest.fixture(scope="module")
def answers():
    return run_demos()


def test_basic_comparison_matches_independent_reference(answers):
    references = json.loads((Path(__file__).parent / "fixtures" / "reference_answers.json").read_text())
    expected = next(c for c in references if c["id"] == "mau-0")
    assert answers[0].results[0].baseline == expected["baseline"]
    assert answers[0].results[0].current == expected["current"]


def test_contribution_reconciles_to_total(answers):
    result = answers[1].results[0]
    assert result.skill == "K2" and result.reconciliation["reconciled"]
    assert sum(r["change"] for r in result.records) == result.absolute_change


def test_agentic_scenario_has_all_skills_and_evidence(answers):
    assert [r.skill for r in answers[2].results] == ["K1","K2","K3"]
    assert all(r.evidence for r in answers[2].results)


def test_quality_scenario_reports_duplicates_freshness_and_completeness(answers):
    result = answers[3].results[0]
    assert result.quality["events"]["raw_rows"] > result.quality["events"]["unique_events"]
    assert result.quality["events"]["late_events"] > 0
    assert all(r["complete"] for r in result.quality["coverage"])
    assert result.quality["freshness_basis"]


def test_followup_preserves_periods_and_filters_market(answers):
    assert answers[4].context.request.market == "Market A"
    assert answers[4].context.request.baseline == answers[0].context.request.baseline
    assert answers[4].context.request.current == answers[0].context.request.current
