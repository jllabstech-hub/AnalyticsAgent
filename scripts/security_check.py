"""Check candidate source files without printing secrets or mutating Git."""
import json
import os
import re
import subprocess
from analytics_agent.config import PROJECT_ROOT, load_settings


def check():
    findings, inspected = [], 0
    ignored = {".venv",".git","__pycache__",".pytest_cache","node_modules"}
    pattern = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}")
    for folder, directories, names in os.walk(PROJECT_ROOT):
        directories[:] = [d for d in directories if d not in ignored]
        for name in names:
            if name == ".env" or name.startswith(".env.") and name != ".env.example": continue
            path = PROJECT_ROOT / os.path.relpath(os.path.join(folder,name),PROJECT_ROOT)
            if path.suffix not in (".py",".md",".yaml",".yml",".toml",".txt",".json") and name != ".env.example": continue
            inspected += 1
            text = path.read_text(encoding="utf-8-sig",errors="replace")
            if pattern.search(text): findings.append({"file":str(path.relative_to(PROJECT_ROOT)),"issue":"possible credential"})
    git_repository = (PROJECT_ROOT / ".git").exists()
    if git_repository:
        tracked = subprocess.run(["git","ls-files","-z"],cwd=PROJECT_ROOT,capture_output=True,text=True,check=True).stdout.split("\0")
        if any(file == ".env" or file.endswith("secrets.toml") for file in tracked): findings.append({"issue":"secret configuration tracked in Git"})
    report = {"status":"pass" if not findings else "fail","candidate_text_files_checked":inspected,"findings":findings,
        "git_repository_present":git_repository,"openai_key_configured":bool(load_settings().openai_api_key),
        "controls":["Typed tool arguments and allowlist","Scope checks including cache hits","Read-only approved SQL templates","Restricted DuckDB file access","Server-side credentials excluded from repr/session","Remote Ollama requires HTTPS and bearer token","No automatic local-to-cloud switch","Private production OIDC and server scope guard fail closed","Opt-in public demo restricts UI to the bundled synthetic warehouse and blocks LLM providers"],
        "limitations":["Source scan plus behavioral tests; not a formal penetration test.","Actual identity-provider login is unverified.","Hosted signed-in analytics and production operation remain unverified."]}
    output = PROJECT_ROOT / "reports" / "security.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


if __name__ == "__main__":
    report = check()
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report["status"] == "pass" else 1)
