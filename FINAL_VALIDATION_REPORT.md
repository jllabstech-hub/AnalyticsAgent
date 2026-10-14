# Final validation report

Updated UTC: 2026-10-14T02:25:18.182168+00:00. Supersedes the initial phase-12 report.

Verdict: **hardened synthetic prototype with verified Free Render startup/restart; production approval still requires broader live-provider, real-identity and hosted analytics validation.**

| Check | Actual result | Evidence |
|---|---|---|
| Full automated suite | 193 passed / 0 failed / 2 skipped; 195 total | reports/test_results.xml; reports/evaluation.json |
| Independent pandas reference comparisons | 30/30 matched | tests/fixtures/reference_answers.json |
| Human-question agent workflows | 30/30 matched | tests/test_e2e_references.py |
| Five EVP workflows | All executed successfully | reports/demo_results.json |
| Synthetic integrity | 100,000 users; 1,186,245 rows; 1,180,343 unique events | data/synthetic/validation_report.json |
| Published dependency advisories | 0 known vulnerability records across 83 scanned packages; no skipped packages | reports/dependencies_audit.json |
| Four simultaneous investigations | 4/4 succeeded with identical totals | reports/performance.json |
| Startup/restart | Two actual HTTP 200 / ok starts | reports/deployment_smoke.json |
| GitHub Linux CI | 193 passed / 0 failed / 2 skipped; credential and dependency scans plus both restarts pass | reports/github_validation.json; Actions run 38508157329 |
| Free Render deployment | Live; root/health HTTP 200; recorded restart and subsequent health pass | reports/render_deployment.json |
| Browser review | Desktop and compact layout, computed charts, quality warnings, Settings failure and Explorer verified | reports/browser_e2e_verification.json |
| Production access | Anonymous, expired/unapproved and malformed grants blocked; scoped UI and revocation regression pass | tests/test_access.py |

Independent comparison accuracy is 100% on the defined synthetic suite. This is not enterprise accuracy or broad live-LLM routing accuracy. The full automated run intentionally disables live opt-in checks. Separate real OpenAI inference, application Test Connection and the August/September K1 browser comparison now pass. Ollama remains unavailable. See reports/openai_live_validation.json for the live evidence and limits.

## Measured execution

Cold three-skill investigation: 7.196s. Warm investigation: 5.683ms. Four simultaneous requests: 7.333–7.334s. Peak backend working set: 385.04 MiB. DuckDB budget: 512MB, one thread and one shared warehouse execution slot; disk spill disabled.

These are Windows backend measurements, excluding hosted behavior and additional Streamlit/LLM overhead. They do not establish sustained traffic capacity. Latest Windows startup times were 1.643s and 1.629s. HTTP health verifies server availability; production sign-in must be separately configured and tested.

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
