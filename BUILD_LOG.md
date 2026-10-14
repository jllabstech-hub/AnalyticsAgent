# Build log

## Phase 1

Created Streamlit shell, settings, dependencies and four smoke tests.
Installed dependencies with `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
Corrected PyArrow 26 conflict with Streamlit by pinning PyArrow 24.0.0.
`python -m pytest -q`: 4 passed. `pip check`: no broken requirements.
HTTP health and browser shell verified.

## Phase 2 started

Decisions: fixed UTC calendar, fictional identifiers, seed 20260701, six Parquet
tables, separate incomplete partition, independent pandas evaluation fixtures.
Primary August/September remains complete; historical freshness is measured at
the documented synthetic snapshot date, not represented as live enterprise data.
NVIDIA diagnostics report GeForce MX330 with 2048 MiB VRAM. Ollama absent from PATH.
A PowerShell inline SQL quoting error was corrected using a literal here-string.
Official DuckDB, Ollama, OpenAI and Render documentation consulted.
Generation validation caught Pandas 3 datetime microseconds being interpreted as
nanoseconds. Fixed by explicitly converting activation timestamps to datetime64[ns].

Phase 2 commands: `python -m scripts.generate_data`, `python -m scripts.validate_data`,
`python -m scripts.reference_answers`, `python -m pytest -q`. Six tests passed.
Data: 100000 users, 1186245 event rows, 5902 duplicates, 23429 late events.

## Phase 3

Ephemeral DuckDB views use trusted bundled files, restricted external access,
locked configuration, two threads, memory bounds, interrupt timeouts and row limits.
Validated typed arguments; permission filters are applied to every analytical call.
Thirty independent comparison cases cover six metrics and five scopes.
First run: five DAU SQL alias failures, corrected alias to activity_day.
Full suite: 42 passed in 33.96s after correction.

## Phase 4 started

YAML definitions and Pydantic K1–K3 results. Rate and overlapping-group deltas
are not reconciled. New/existing cohorts change membership at each period start.
Skill tests caught a second reserved alias in the trend template; changed it to
active_users. Added runtime join-cardinality validation and symmetric period coverage.
`python -m pytest tests/test_skills.py -q`: 8 passed in 18.97s.

## Phase 5 started

REST Ollama adapter uses installed requests; no extra SDK, installation or model
download. HTTPS plus server token required for remote origins. Cloud Ollama
origins rejected. Structured output and tool-call responses require Pydantic validation.
`python -m pytest tests/test_ollama.py tests/test_config.py -q`: 10 passed in 0.42s.
`python -m scripts.diagnose_llm --inference`: local endpoint unreachable; actual
inference remains unverified. No installer or model download initiated.

## Phase 6 started

Common adapter interface and ProviderManager. OpenAI SDK max_retries=0; bounded
timeouts. Only missing-key, timeout, connection and temporary service failures
can fallback to reachable Ollama with the configured model. Authentication,
invalid requests and invalid tool output never fallback. Cloud calls are not
made by startup or passive status checks.
`python -m pytest tests/test_providers.py tests/test_ollama.py tests/test_config.py -q`:
23 passed in 0.93s. Live OpenAI inference is not attempted.

## Phase 7 started

Validated LLM plan tool selects K1–K3. Numeric explanations use computed facts;
LLM may select/order evidence IDs but cannot author numerical answers. Same
skills in all modes. Explicit deterministic parser covers documented questions.
Context contains only the last authorized request. Limits enforced before tools,
with request deadline propagated to DuckDB interrupt timers.
`python -m pytest tests/test_agent.py -q`: 9 passed in 18.86s.

## Phase 8 started

Streamlit presentation separated into ui.py. App entry point stays minimal.
Initial combined delete/add patch was rejected; no files changed by that attempt.
Workspace: query-backed KPIs, Plotly, findings, evidence and execution status.
Settings: nonsecret preferences only; API keys stay in server configuration.
Explicit demo mode remains off by default. Read-only Data Explorer and evaluation
dashboard added. Supporting trend is explicitly labelled daily active users.
`python -m pytest tests/test_app.py tests/test_ui.py -q`: 3 passed in 5.00s.

## Phase 9 started

Added independent hand-calculated small warehouse tests for boundaries, actual
zero denominators, overlapping device/membership groups, time-valid joins,
zero-day DAU, stale data, row limits, deadline and restricted file access.
Live-provider tests require explicit opt-in. Aggregate evaluation is derived
from actual JUnit output, not hand-entered pass counts.
`python -m scripts.evaluate`: 90 passed, 2 skipped, 0 failed; all 30 analytical
references matched. Two skips are explicitly gated live LLM tests.

## Phase 10 started

Render YAML uses the exact requested start command, assigned PORT, bundled
Parquet and no persistent disk; autoDeploy disabled and free plan selected.
Added two-start HTTP smoke, startup PowerShell and measured local benchmark.
Integrated browser caught stale settings in the long-running Phase 1 server;
stopped that server to restart with fresh imports. A patch hunk ordering failure
made no changes and was corrected by applying ordered hunks.
`python -m pytest tests/test_deployment.py tests/test_ui.py -q`: 4 passed.
256MB benchmark failed in global cardinality validation. Replaced simultaneous
million-event hash sets with bounded temporal-key checks and separate streaming
source/matched counts. Kept no disk spill and did not hide the memory failure.
Temporal-key and restart tests passed (11 tests), but 256MB still failed in a
full-event temporal join. Reduced DuckDB to one thread and disabled unnecessary
insertion-order preservation; validating the same analytical semantics again.
One-thread 256MB still failed. Chose the tested 512MB DuckDB budget and prepared
a 2GB Render plan rather than misrepresent free-tier compatibility. YAML alone
does not provision anything; applying it requires paid/public-hosting authorization.
512MB benchmark passed: K1 4.40s, K2 4.70s, K3 4.99s; multi-step 12.92s;
backend peak working set 384.0 MiB. Actual HTTP restart smoke passed twice,
startup 1.196s and 1.199s. No persistent database files or hosted deployment.

## Phase 11 started

Created executable five-scenario package and guide. Tests execute all five with
the same skills and compare key results against independent evaluation fixtures.
`python -m pytest tests/test_deployment.py tests/test_demo_workflows.py -q`:
7 passed in 30.44s; all five complete demonstrations executed successfully.

## Phase 12 integration review

Cache immutable approved query outputs by request, scope, period, dataset size/
mtime and resource limits; authorization runs even on cache hits. Cache is bounded
to 32 entries, returns independent copies, and labels cached query evidence.
Default backend mode follows configured Ollama; deterministic mode must be explicit.
Test Connection now uses the same safe provider fallback policy as analysis.
OpenAI per-request timeout is explicit; raw provider error bodies are never logged.
Quality device counts now use time-valid joins. Patch context mismatch was corrected
without partial file changes. Final regression, security and browser checks pending.
Affected integration tests after caching: 33 passed in 26.22s.
Review identified Streamlit widget cleanup could reset provider preferences when
leaving Settings. Applied documented temporary-widget/durable-session-key pattern
and added navigation regression. OpenAI model selector accepts explicit custom
model names rather than recommending an unrelated deprecated alternative.
Coverage gaps are now warned even when the metadata row itself is missing.
Provider fallback is latched locally for the remainder of an answer; subsequent
explanation does not silently retry cloud. Propagated investigation deadline to
provider budgets. Model planning receives YAML business semantics, never fixtures.
Evidence sources now correspond to the executed template rather than all datasets.
Additional numeric validation checks finite outputs and numerator/denominator
population bounds; temporal keys validate dates and referenced markets. Explorer
samples respect the configured result limit. Final source map includes the
market reference used by temporal-key validation.
`python -m scripts.evaluate`: 104 passed, 2 skipped, 0 failed (97.04s).
All 30 independent reference questions matched. Final browser/restart and final
documentation generation remain in progress.
Final review added a regression for malformed model explanation JSON. It failed
with AttributeError and withheld valid computed results. Fixed by validating the
explanation selection through Pydantic and retaining computed findings on failure.
Settings now distinguishes safe provider error codes from reachability claims,
records attempted fallback reasons, and discovers installed models after a
successful connection test. No raw SDK error body or credential is displayed.
Malformed-explanation regression now passes; affected suite: 20 passed.
Full suite after the fix: 105 passed, 2 skipped, 0 failed (100.50s).
Final routing review prevents unknown follow-up subjects from inheriting MAU;
added weather/email context cases. Browser validated KPI/chart, explicit providers,
safe missing-key failure and read-only 100000-user explorer at 1366x900.

Final routing/full regression: 107 passed, 2 skipped, 0 failed; 30 reference questions matched.
Final benchmark: cold 6.984s, warm 8.222ms, backend peak 382.49 MiB.
Repeated real Render-style smoke: two 200/ok starts; no persistent DB. Browser inspected desktop workspace, safe provider failures, settings persistence and explorer. Saved screenshots and restored viewport.
Generated FINAL_VALIDATION_REPORT.md and refreshed IMPLEMENTATION_STATUS.md from measured JSON/XML evidence. README, ARCHITECTURE, DEMO_GUIDE and DEPLOYMENT_GUIDE complete. Git rev-parse confirms no repository; pip check clean. No external publishing, billing or model installation.
Final local server restarted with current routing code and left running on 127.0.0.1:8501. Compact browser required opening the collapsed sidebar before toggling demo mode. A selector wait expired during calculation; fresh AX state verified the completed 66025/65292 result and Plotly chart. Browser tab retained as deliverable. No publishing or model downloads performed.

### 2026-10-14 — Reported Settings attribute error / browser recovery
User screenshot showed Settings.llm_provider AttributeError from the earlier UI line 139 and a CONNECTING indicator. Current source imports successfully with provider=ollama; current ui.main begins at line 146. Direct health request to http://127.0.0.1:8501/_stcore/health returned 200/ok. Read-only process inventory was denied by the sandbox; no unrelated process was stopped. No server restart or source workaround was necessary.
Ran `.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_app.py -q`: 4 passed in 1.64s. Reloaded the existing browser tab, verified a fresh Ollama-default session without an exception, then explicitly enabled deterministic demo mode and executed the August/September comparison. Browser displayed MAU 66,025 / 65,292, change -733 (-1.11%), provider=deterministic demo, and the Plotly trend. Saved reports/browser-recovery.jpg and retained the working tab. This recovery adds no live LLM inference or hosted deployment claim.

### 2026-10-14 — End-to-end quality audit and hardening
Baseline `python -m scripts.evaluate`: 107 passed, 2 skipped, 0 failed. Read all runtime modules, data validation/reference scripts, deployment configuration and tests. Added hand-calculated audit regressions before fixes: 15 failed / 2 passed. Reproduced service routing, ignored unknown filters/day boundaries, new-vs-existing intent, zero-day trend omission, device adoption population mismatch, missing execution-period evidence, rate units, fallback model/reason, hardcoded follow-up periods/scope and nonfinite budgets.
Fixed shared engine/parser/skills/provider-output paths. Adoption v1.1 now requires actual simultaneous membership/device validity; new/activation metrics retain the documented period-end device rule. Calendar charts include genuine zeros and preserve missing-data gaps. Conflicting duplicate payloads, impossible ingestion times and orphan relationships withhold results. Added serialized warehouse sessions, coalesced duplicate work and metric-independent quality/trend caches with request-correct evidence.
Added production OIDC guard using Streamlit/Authlib, issuer+subject access scopes and identity expiration. Missing configuration, unapproved identity and malformed grants stop before provider/data controls. Render forces production mode. Scope changes clear retained conversation/results. Actual IdP login remains unverified. Added wrapping KPI cards, percentage-point chart units, visible provisional warnings and configuration errors without traceback.
Installed Authlib 1.8.0 into project venv. Initial sandboxed pip attempt failed with WinError 10013; approved PyPI installation succeeded. Pin added to requirements. `pip check`: clean. Added server secret template and Render Secret File lookup.
Targeted initial hardening/edge suite: 29 passed. Provider/UI/hardening suite: 21 passed. Access tests initially failed because the tiny test warehouse lacked manifest.json; fixed the fixture, 13 access tests pass. A new incomplete-scenario UI case exposed an overstrict filter clause; explicitly allowed the documented scenario suffix, regression passes. Agent reference run: 53 passed (30 actual natural-language workflows included). Full final regression, dependency audit, benchmark and browser review in progress. No real key copied, public publishing, billing resources or model downloads.

Final output review found malformed Ollama model-discovery JSON could raise raw exceptions. Three regressions failed before correction; model names/list shape now validate and return safe ProviderError. Owned HTTP clients close after answers/settings tests. A real browser connection test exposed stale fallback reason after an earlier demo; regression failed, then latest-operation status tracking fixed it. UI suite: 7 passed.
Final full suite on completed runtime source: 183 passed, 2 skipped, 0 failed of 185 (154.57s). Independent comparisons 30/30; natural-language deterministic workflows 30/30. Actual provider diagnostics still show no replacement OpenAI credential and unreachable Ollama; no successful live inference is claimed.
Installed pip-audit 2.10.1 as a development tool; first live scan found four feed records representing two distinct pip advisories. Updated project pip 26.1.1 to 26.2.1; repeat scan: 83 packages, zero known findings, zero skipped packages. pip check clean. Updated Render build installer command and added a prepared Linux GitHub Actions quality workflow using current official action references. Parsed YAML locally; no repository/push/hosted CI run occurred.
Benchmark: cold 7.196s; warm 5.683ms; four simultaneous shared-engine requests all passed in 7.333–7.334s; peak backend 385.04 MiB. Final startup/restart smoke: 200/ok twice (1.264s, 1.178s), port 8765, no persistent DB.
Final browser verified computed 66025/65292/-733, market/cohort reconciliation and three skill traces. Incomplete scenario displayed 62411 with provisional chat/top warning and missing-day graph gaps. Settings reported both_unavailable/missing_key with the latest reason visible after a demo; restored Ollama selection. Explorer showed 100000 users/schema/sample; Evaluation Dashboard showed actual 185/183/2 results. Restored normal compact viewport: KPI values fully visible without ellipsis. Browser retained in explicit demo mode.
Browser automation recovery: a Playwright screenshot captured only the header; the documented getScreenshot API captured the complete view. Expander is a DOM generic/summary rather than a button; used observed text locator after inspecting the DOM. These were harness issues, not fabricated application successes. Saved five browser-e2e screenshots and browser_e2e_verification.json.
Refreshed FINAL_VALIDATION_REPORT.md, PRODUCTION_READINESS.md and IMPLEMENTATION_STATUS.md from measured reports. Documented real model, identity-provider and hosted/expected-load validation as production approval blockers. No posted key was copied, public site published, paid resource created or Ollama/model installed.


### 14 October 2026 - Team architecture Word handover

Created deliverables/BDC_Analytics_Agent_Architecture_and_Technical_Handover_V1.docx with bundled python-docx. Verified current source, schemas, metric YAML, configuration, deployment and existing reports. Sixteen pages include two diagrams and nineteen tables. Standard render_docx.py failed because the Windows bundle has no LibreOffice. Native Word background export required approved desktop-session execution; process-scoped PowerShell policy handled the trusted helper. Corrected COM close by-reference handling and tolerated only the documented RPC-already-exited cleanup condition. Used packaged render_docx.py rasterization with bundled Poppler and inspected every final page image. Shortened a wrapping table label, added data relationships and an executable skill example, and rendered/reviewed the full revision. Accessibility audit: zero findings. Example executed against bundled synthetic data: K1 MAU 66025 to 65292, delta -733. Credential candidate check: zero. No application code, live LLM configuration, or deployment changed. QA evidence is deliverables/architecture_qa/final_document_validation.json; only the DOCX is delivered.


### 2026-10-14T01:56:56.265839+00:00 - OpenAI configuration and actual live workflow

User supplied a credential for troubleshooting. Saved only OPENAI_API_KEY in ignored .env; no value copied to source or this log. Default provider remains Ollama; OpenAI was selected explicitly in the browser. One direct SDK check returned HTTP 200, then application Test Connection verified actual inference. Initial real comparison selected end-of-month dates as exclusive ends and repeated K3 tasks, causing StreamlitDuplicateElementId. Added tests first: 5 failed, 1 passed. Fixed approved-question semantics after original-plan authorization, supplied explicit skill/month guidance, coalesced identical tasks, and keyed result charts/tables. Targeted regression/agent/explanation/UI suite: 25 passed. Added day-level preservation case; full python -m scripts.evaluate with live opt-in disabled: 190 passed, 0 failed, 2 skipped of 192; 30/30 independent and 30/30 question references. python -m scripts.smoke_deployment --port 8765: two HTTP 200/ok starts. Restarted owned server; real browser Test Connection passed. Corrected real K1 comparison returned 66025 / 65292 / -733 with OpenAI, no fallback, demo off and no UI exception; public trace 49.12 seconds. Source docs and status updated; live evidence in reports/openai_live_validation.json. API errors/keys were not printed. Original key is exposed in chat and must be rotated by the owner. No paid hosting, model download or public deployment created.


### 2026-10-14T02:01:04.773939+00:00 - Local Ollama troubleshooting

Checked CLI PATH, standard user/Program Files paths, installed-program registry entries, process list, local /api/tags endpoint and standard model manifests. No Ollama executable/registration/process/model manifests found; port 11434 unreachable. Hardware: 31.73 GiB RAM, 16.07 GiB available at check, NVIDIA MX330 2048 MiB. Fixed a read-only hardware query quoting error by using a Python here-string. OpenAI server configuration remains present (boolean only). Official Windows documentation states at least 4 GB installation disk; official qwen3:1.7b listing is about 1.4 GB. Requested explicit installation/model download authorization under the original build instruction; no download/install or cloud inference performed. Readiness evidence: reports/ollama_local_readiness.json.


### 2026-10-14 - Authorized GitHub source delivery preparation

User authorized source upload to https://github.com/jllabstech-hub/AnalyticsAgent. Verified that the public repository is empty and the existing Git credential has push permission, without printing credentials. Initialized main and configured origin. Excluded .env, virtual environments, model downloads and document-render intermediates. Refreshed the sixteen-page team handover from the current 192-test evidence and actual OpenAI K1 verification; Word render and accessibility audit pass. Source staging, final credential scan, commit, push and hosted CI verification follow. No Ollama installation/model download or application deployment is authorized by this source-upload request.

Pre-commit checks: source scan passed (80 candidate text files); staged blob scan passed for all 98 files including DOCX XML; no credential patterns, forbidden local files or GitHub-oversized blobs. Staged content totals 62.52 MiB; largest Parquet blob 29.85 MiB. git diff --cached --check is clean. .env, .venv and architecture QA intermediates are confirmed ignored.


### 2026-10-14 - First remote verification and Linux smoke correction

Initial main push succeeded; local and remote SHA ecbba602ae0860723be808d9d252c7ebfa45c208 match and origin/main tracking is configured. GitHub Actions run 38500057487 actually passed 190 tests with 2 skipped (95.21s), source credentials and dependency advisory checks, then failed its second startup port preflight with Linux Errno 98. Updated POSIX port availability checks to allow TIME_WAIT reuse while still rejecting active listeners, and made smoke report platform wording accurate. Added a real two-start health/restart regression. First remote log display hit Windows cp1252 UnicodeEncodeError; UTF-8 stdout fixed the read-only harness. Full regression and corrected Linux CI follow.

Local new restart regression initially failed because sandboxed taskkill could not terminate its temporary server. Interrupted the subsequent evaluation and stopped only the identified owned test process. Elevated pytest then needed a separate temporary directory to avoid sandbox-owned pytest temp ACLs. Targeted deployment suite with isolated temp and cache disabled: 4 passed (4.77s). Current full suite restarted under the same valid conditions. This harness restriction is distinct from the corrected Linux TIME_WAIT issue.

Final Windows regression after Linux smoke correction: 191 passed, 0 failed, 2 skipped of 193 (174.12s). Independent calculations and natural-language reference workflows both remain 30/30. Actual main application smoke with Render flags: two HTTP 200/ok starts, 1.643s and 1.629s. Corrected source commit 2060e661aa98b2a8443a21a1d90ed0dcade7e336 pushed and remote SHA verified. Linux workflow 38500606126 remains in progress at the last check.


### 2026-10-14 - GitHub delivery and Linux quality verification complete

Application source is pushed to main at jllabstech-hub/AnalyticsAgent and tracked as origin/main. Corrected source commit 2060e661aa98b2a8443a21a1d90ed0dcade7e336 matches the remote. Actual GitHub Actions run 38500606126 passed all steps: 191 passed, 0 failed, 2 skipped of 193 in 142.91s, credential source check, zero known dependency advisories and two Linux HTTP 200/ok startup/restart checks. Final Windows suite also passed 191/0/2 (174.12s); both 30-question reference suites remain 30/30. Sanitized remote evidence is reports/github_validation.json. Updated team handover reflects current counts and Linux CI. No credentials are tracked; local .env remains ignored. Ollama installation/model download, real IdP lifecycle and Render/paid hosting remain separately pending. Final evidence-only commit will skip duplicate CI because application runtime source is unchanged.

Final delivery document QA: rendered 16 pages, visually inspected every final page at original resolution, nineteen tables and two diagrams retained; accessibility findings zero, DOCX XML credential candidates zero. Documentation/evidence-only updates preserve the verified runtime source.


### 2026-10-14T02:35:19.202606+00:00 - Render deployment preparation

User authorized Render deployment. Inspected the signed-in Render workspace and prepared the new Web Service form from the public repository, main, Python 3.14.5, Singapore, tested build/start commands, 1c-2g (displayed US$25/month), production guard, health path and manual deploys. No creation/charge has occurred. Existing local OIDC secrets file is absent; analytics stays locked until real login and scopes are configured. No OpenAI key has been copied to Render. Automatic approval review rejected a planned localhost Ollama endpoint because the laptop is unreachable from Render. Corrected the form and Blueprint to an explicitly empty endpoint; no network calls target an invented remote service. Full-page screenshot timed out; supported viewport capture succeeded. Saved the review screenshot and requested explicit recurring-cost approval plus login/deployment preference. Configuration/access tests running.

Prepared Render configuration and production access regression: 17 passed, 0 failed (7.62s). Source credential scan passes. No production auth bypass, credential transmission or paid service creation. The prepared Ollama endpoint is intentionally empty; authorized users can explicitly select deterministic demo mode until a real provider is configured.

Public push of the unpublished preparation commit was rejected by automatic approval review because a Render dashboard screenshot could disclose private account metadata. Kept that screenshot local and excluded it from Git, removed the private workspace label from preparation metadata/docs, and will amend the unpushed commit before retrying. No remote disclosure occurred.
