"""Run real tests and derive aggregate evaluation from the generated JUnit report."""
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from analytics_agent.config import PROJECT_ROOT


def evaluate():
    output = PROJECT_ROOT / "reports"
    output.mkdir(exist_ok=True)
    started = time.perf_counter()
    completed = subprocess.run([sys.executable,"-m","pytest","-q",str(PROJECT_ROOT / "tests"),f"--junitxml={output / 'test_results.xml'}"],cwd=PROJECT_ROOT)
    cases = ET.parse(output / "test_results.xml").getroot().findall(".//testcase")
    failed = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    skipped = [c for c in cases if c.find("skipped") is not None]
    references = [c for c in cases if c.attrib["name"].startswith("test_independent_reference_comparisons[")]
    correct = sum(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in references)
    e2e = [c for c in cases if c.attrib["name"].startswith("test_natural_language_reference_e2e[")]
    e2e_correct = sum(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in e2e)
    sales = [c for c in cases if c.attrib["name"].startswith("test_independent_sales_references[")]
    sales_e2e = [c for c in cases if c.attrib["name"].startswith("test_natural_language_sales_reference_e2e[")]
    business = [c for c in cases if c.attrib["name"].startswith("test_independent_business_references[")]
    business_e2e = [c for c in cases if c.attrib["name"].startswith("test_natural_language_business_reference_e2e[")]
    def correct_count(items): return sum(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in items)
    report = {"generated_at_utc":datetime.now(timezone.utc).isoformat(),"total":len(cases),"passed":len(cases)-len(failed)-len(skipped),"failed":len(failed),"skipped":len(skipped),
        "reference_questions":len(references),"correct_reference_questions":correct,"analytical_accuracy_defined_suite":correct/len(references) if references else None,
        "natural_language_e2e_questions":len(e2e),"correct_natural_language_e2e_questions":e2e_correct,
        "sales_reference_questions":len(sales),"correct_sales_reference_questions":correct_count(sales),
        "sales_natural_language_e2e_questions":len(sales_e2e),"correct_sales_natural_language_e2e_questions":correct_count(sales_e2e),
        "marketing_finance_reference_questions":len(business),"correct_marketing_finance_reference_questions":correct_count(business),
        "marketing_finance_natural_language_e2e_questions":len(business_e2e),"correct_marketing_finance_natural_language_e2e_questions":correct_count(business_e2e),
        "test_duration_seconds":round(time.perf_counter()-started,3),"limitations":["Synthetic evaluation only; not enterprise production accuracy.","Live LLM inference requires services, credentials and explicit opt-in.","DAU charts are supporting engagement trends for other metrics.","OIDC and server scope guards tested with claims; actual identity-provider login remains unverified."],
        "skipped_reasons":[c.find("skipped").attrib.get("message","") for c in skipped]}
    (output / "evaluation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(evaluate())
