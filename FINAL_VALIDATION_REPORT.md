# Final validation report

Updated 14 October 2026 for four-domain application source a8203bc65066decdaabf5432b58e69b098f905b5. Supersedes the initial phase-12 and two-domain release reports. Dated sections below preserve implementation history.

Verdict: **hardened four-domain synthetic prototype with actual public Free Render workflows and startup/restart; production approval still requires broader live-provider, real-identity and hosted capacity validation.**

Local OpenAI follow-up: the owner reported a connection failure in the running app
after standalone and AppTest inference succeeded. Those tests had approved network
access; the server had inherited restricted access (Windows error 10013). After
restarting only the localhost:8502 server with approved network access, the owner
confirmed **Inference connection verified** in the actual app. This confirmation
does not add a new analytical accuracy or latency measurement. No application
source, public Render configuration or full-suite result changed.
See `reports/local_openai_network_recovery.json` for the test-method distinction.

| Check | Actual result | Evidence |
|---|---|---|
| Full Windows automated suite | 462 passed / 0 failed / 2 skipped; 464 total; 271.72s pytest | reports/test_results.xml; reports/evaluation.json |
| Independent pandas reference comparisons | Usage 30/30; Sales 40/40; Marketing/Finance 55/55 matched | tests/fixtures/reference_answers.json; tests/fixtures/sales_reference_answers.json; tests/fixtures/business_reference_answers.json |
| Human-question agent workflows | Usage 30/30; Sales 40/40; Marketing/Finance 55/55 matched | tests/test_e2e_references.py; tests/test_sales_pipeline.py; tests/test_business_domains.py |
| Demonstration workflows | All twenty documented local demos; 140 completed components; ten new-domain hosted demos | reports/four_domain_pipeline_trace.json; reports/four_domain_hosted_verification.json |
| Synthetic Usage integrity | 100,000 users; 1,186,245 activity rows; 1,180,343 unique events | data/synthetic/validation_report.json |
| Synthetic Sales integrity | 25,000 orders; 50,000 canonical lines; 500 duplicates; 1,987 late lines | data/synthetic_sales/validation_report.json |
| Synthetic Marketing integrity | 60,000 canonical observations; 600 duplicates; 3,095 late observations | data/synthetic_marketing/validation_report.json |
| Synthetic Finance integrity | 30,000 booked transactions; 300 duplicates; 1,465 late transactions | data/synthetic_finance/validation_report.json |
| Published dependency advisories | 0 known vulnerability records across 86 scanned packages; no skipped packages | reports/dependencies_audit.json |
| Four simultaneous investigations | 4/4 succeeded with identical totals | reports/performance.json |
| Four-domain UI/export memory | 423.57 MiB peak on Windows; one process; 320MB DuckDB; not hosted capacity | reports/four_domain_memory_smoke.json |
| Startup/restart | Two actual local HTTP 200 / ok starts; actual hosted restart and four fresh domain comparisons | reports/deployment_smoke.json; reports/four_domain_hosted_restart_health.json |
| GitHub Linux CI | 459 passed / 0 failed / 2 skipped; 153.62s; credential and dependency scans plus both restarts pass | reports/github_validation.json; Actions run 38560216690 |
| Free Render deployment | Four-domain demo Live; ten new-domain workflows, seven components, downloads and new-domain Explorer pass; fresh four-domain references pass after restart; root/health HTTP 200 | reports/render_deployment.json; reports/four_domain_hosted_verification.json |
| Independent hosted numbers | Ten Marketing/Finance totals, trends and groups pass 107 numerical comparisons; four post-restart totals add 12 comparisons | reports/four_domain_hosted_reference_check.json |
| Browser review | Desktop and compact layout, computed charts, quality warnings, Settings failure and Explorer verified | reports/browser_e2e_verification.json |
| Production access | Anonymous, expired/unapproved and malformed grants blocked; scoped UI and revocation regression pass | tests/test_access.py |

Independent comparison accuracy is 100% on the defined synthetic suite. This is not enterprise accuracy or broad live-LLM routing accuracy. The full automated run intentionally disables live opt-in checks. Separate real OpenAI inference, application Test Connection and the August/September K1 browser comparison now pass. Ollama remains unavailable. See reports/openai_live_validation.json for the live evidence and limits.

## Historical Usage benchmark

Earlier Usage-only backend measurement: cold three-skill investigation 7.196s; warm 5.683ms; four simultaneous requests 7.333–7.334s; peak 385.04 MiB at a 512MB DuckDB budget. The current Free configuration is 320MB, one thread and one process-wide warehouse execution slot; disk spill disabled. Actual four-domain UI/export peak is 423.57 MiB.

These are Windows backend measurements, excluding hosted behavior and additional Streamlit/LLM overhead. They do not establish sustained traffic capacity. Latest public-mode Windows startup times were 1.311s and 1.231s. Public Free hosted queries took 43.08s for the first comparison and 44.14s after restart; later cached comparisons are faster. Private production sign-in must be separately configured and tested.

## Corrections verified in this audit

- Adoption v1.1 aligns numerator/denominator device populations and requires actual membership/device temporal intersection.
- Zero-activity calendar days are present; incomplete days are null gaps. Provisional coverage is visible in both chat and above KPI cards.
- Unknown filters/day-level demo requests cannot silently select a different population. Service breakdowns and new/existing cohorts route correctly.
- Query evidence includes actual executed periods, groupings and authorized scope, including cache hits.
- Ratio deltas use percentage points. All grouped populations receive denominator and finite-number checks.
- Conflicting duplicate payloads, impossible ingestion timestamps and invalid/orphan joins withhold findings.
- Shared execution is bounded; concurrent identical work is coalesced; quality/trends reuse safe scope-specific caches across metrics.
- Fallback labels preserve the actual provider/model and latest failure reason. Model selections cannot remove the computed primary observation.
- Owned provider HTTP clients close after use; malformed Ollama discovery responses become safe provider errors.
- Production mode requires OIDC plus a server-owned issuer/subject scope map. Missing/expired identities and invalid grants deny access before analytics/LLM controls. Scope changes clear prior answers.
- KPI cards wrap at compact widths. Backend source watching is disabled; clean restarts avoid stale imported configuration classes.
- pip advisories were resolved by upgrading the project installer to 26.2.1. The repeat scan reports zero known issues; this is not a security certification.

## External verification still required

1. Rotate the exposed OpenAI key and expand live reference/failure-path evaluation. One real OpenAI K1 question has succeeded; live Ollama and broader live accuracy still require verification.
2. Register a real OIDC client and verify HTTPS login/logout, returned claims, expiry, revoked accounts and scoped data behavior. Current authentication tests use simulated verified claims.
3. After OIDC setup, verify authenticated analytics, memory, concurrency and monitoring on the already-deployed Free service. Source upload, Linux CI and hosted startup/restart are verified; paid resources remain unauthorized.
4. Keep this release synthetic-only. Real enterprise data accuracy, lineage and operational controls require a separate approved integration/evaluation.

Full audit and release gates: PRODUCTION_READINESS.md. Setup: README.md and DEPLOYMENT_GUIDE.md.


## 2026-10-14T01:56:56.265839+00:00 Live OpenAI follow-up

Successful SDK inference and Settings Test Connection. Actual browser K1 comparison uses gpt-4.1-mini-2025-04-14, complete August/September end-exclusive periods, and computed MAU 66025 / 65292 / -733. One approved skill completed in 49.12 seconds, demo mode off, no fallback or UI exception. Full offline regression suite after live fixes: 190 passed, 0 failed, 2 skipped of 192. Initial live plan drift and duplicate chart failures were reproduced before correction. This establishes this single real workflow; it does not establish broader live-model accuracy. Server key rotation and the other release requirements remain necessary.


## Sales pipeline extension - exact-source acceptance

The new sales pack implements the supplied seven-stage core workflow with fictional products/markets and read-only Parquet views. All 40 independent pandas calculations and 40 actual sales question workflows match. Existing usage references remain 30/30 each. New 308-test Windows suite: 306 passed, zero failed, two opt-in live-provider checks skipped. Five sales demonstrations execute and produce seven completed component events; source schemas, validated plans, SQL parameters, numerical checks and output evidence are inspectable. See PIPELINE_COMPONENT_TRACE.md and reports/sales_pipeline_trace.json.

The primary example returns net sales of USD 1,748,539.73 in Q2 and USD 3,218,017.11 in Q3 for Orion One / Market A (+84.04%). These values are generated by approved queries, not supplied reference answers. Local both-domain UI/export peak is 424.27 MiB with 320MB DuckDB. The PDF report is two pages, rendered and visually checked; exports operate in memory. The current startup/restart smoke passes 200/ok twice. New-source GitHub CI and actual Free hosted sales verification now pass; the final section records exact source and evidence. Enterprise connectors, message channels, real Sales LLM inference and sustained hosted load are not established by this synthetic test.


## Historical two-domain hosted evidence

Runtime source 94bbe25 is Live on Free Render. Five Sales workflows pass after a real service restart at 16:21 Asia/Calcutta; all totals, monthly chart values and group values match independent pandas calculations. Seven component events complete on every workflow. The preserved Usage comparison also returns 66025 / 65292 / -733, with seven completed components (36.946s). The Sales example takes 3.704s; the other Sales cases range from 3.552s to 4.855s. CSV/Excel/PDF/JSON downloads and Sales Explorer are actually verified. Long currency cards were corrected and visually checked; phone width and viewport restoration are recorded. Full corrected-source tests pass on Windows (306/0/2, 222.71s) and Linux CI (306/0/2, 127.30s), including scans and startup/restart. Final local startup smoke passes twice. Reports/platform_hosted_verification.json and its six downloaded traces contain actual evidence. Earlier pending statements describe intermediate gates and are superseded by this section. Public mode uses no LLM; this does not establish real enterprise integrations, live Sales provider behavior or sustained hosted capacity.


## 2026-10-14T11:54:50.189856+00:00 - Four-domain local acceptance

Full exact-source Windows suite: 459 passed, zero failed, two opt-in live-provider
skips of 461 (263.38s pytest; 264.661s evaluator). Usage references 30/30 and human
questions 30/30; Sales 40/40 and 40/40; Marketing/Finance 55/55 and 55/55. Twenty
documented workflows execute with 140 completed component events under the
320MB/100-row budget. Actual four-domain UI/export peak is 423.57 MiB. Final
startup/restart smoke is 200/ok twice (1.379s, 1.155s). New-domain malformed sources,
unauthorized scopes, SQL/binding tampering, zero denominators, incomplete periods,
provider arguments and context switching are tested. Linux CI and actual four-domain
hosted acceptance follow; prior hosted evidence above belongs to the two-domain release.

## Final four-domain hosted acceptance

Runtime a8203bc is Live on the existing Free Render service (1m58s displayed deploy
duration; Live at 17:30 Asia/Calcutta). All five Marketing and five Finance
questions pass, including Aug/Sep and contextual entity follow-ups. Independent
pandas calculations match every total, monthly value and contribution group in
their downloaded traces (107 numerical comparisons). Seven component events
complete on all ten workflows. New-domain Explorer shows 60,600 Marketing and
30,300 Finance physical rows with actual schemas and fictional samples. Hosted
CSV, Excel and PDF downloads reopen; rates retain percentage formats and pp
changes, finance retains USD values, and all seven components appear in exports.

Render records an actual service restart at 17:48 Asia/Calcutta. Fresh comparisons
then match all four independent domain references: Usage 66,025 to 65,292
(42.760s), Sales USD 1,748,539.73 to 3,218,017.11 (4.254s), Marketing CTR 14.11%
to 14.41% (4.049s), Finance modeled profit USD 4,003,078.54 to 2,896,087.27
(3.209s). All seven components complete again; root and health return 200/ok.
Evaluation Dashboard displays the actual 461/459/0/2 report and four registered
domains. Final code is unchanged from the passing Windows and Linux suites.
This acceptance supersedes earlier pending new-source CI/hosted statements.

Finance is a modeled booked revenue/expense subtotal, not audited net income or
a double-entry ledger. Public mode uses no LLM. Real sources, messaging channels,
actual identity lifecycle, live business-domain provider inference and sustained
hosted capacity remain outside verified synthetic acceptance.


## Current local OpenAI Settings verification - 14 October 2026

The local app on port 8502 restores provider Settings on normal startup and has a visible LLM Settings button. Public demo mode still hides that control and blocks provider initialization. Owner confirms Settings is visible. Server credentials remain outside session/rendered text, and the current key successfully completes one real OpenAI connection test (46.423s). A real-provider AppTest Finance F1 comparison returns USD 4,003,078.54 to 2,896,087.27, matching independent pandas values with seven completed components (44.625s, gpt-4.1-mini-2025-04-14). Those individual checks are separate from the offline suite.

Final Windows suite: 462 passed, zero failed, two opt-in live-provider skips of 464 (271.72s; 272.920s evaluator); all 125 independent and 125 human reference questions match. Initial test collection walked protected historical QA folders; evaluation now explicitly selects tests/. A restricted-run smoke subprocess shutdown failed, then the exact check and complete suite passed with the needed Windows process permissions. The orphan test server was cleaned up; the owner app remains healthy. Prior Linux/Free evidence above remains tied to the deployed four-domain source; this local configuration change has not been deployed to the public service.

Reports/local_openai_settings_validation.json, local_openai_finance_validation.json and local_openai_finance_trace.json record actual checks. Live Ollama, Marketing/Sales model workflows and broader provider accuracy remain unverified.
