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
    completed = subprocess.run([sys.executable,"-m","pytest","-q",f"--junitxml={output / 'test_results.xml'}"],cwd=PROJECT_ROOT)
    cases = ET.parse(output / "test_results.xml").getroot().findall(".//testcase")
    failed = [c for c in cases if c.find("failure") is not None or c.find("error") is not None]
    skipped = [c for c in cases if c.find("skipped") is not None]
    references = [c for c in cases if c.attrib["name"].startswith("test_independent_reference_comparisons[")]
    correct = sum(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in references)
    e2e = [c for c in cases if c.attrib["name"].startswith("test_natural_language_reference_e2e[")]
    e2e_correct = sum(c.find("failure") is None and c.find("error") is None and c.find("skipped") is None for c in e2e)
    report = {"generated_at_utc":datetime.now(timezone.utc).isoformat(),"total":len(cases),"passed":len(cases)-len(failed)-len(skipped),"failed":len(failed),"skipped":len(skipped),
        "reference_questions":len(references),"correct_reference_questions":correct,"analytical_accuracy_defined_suite":correct/len(references) if references else None,
        "natural_language_e2e_questions":len(e2e),"correct_natural_language_e2e_questions":e2e_correct,
        "test_duration_seconds":round(time.perf_counter()-started,3),"limitations":["Synthetic evaluation only; not enterprise production accuracy.","Live LLM inference requires services, credentials and explicit opt-in.","DAU charts are supporting engagement trends for other metrics.","OIDC and server scope guards tested with claims; actual identity-provider login remains unverified."],
        "skipped_reasons":[c.find("skipped").attrib.get("message","") for c in skipped]}
    (output / "evaluation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(evaluate())
