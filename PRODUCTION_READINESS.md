# Production readiness assessment

What this repo does: It answers governed questions over 100,000 fictional accounts using approved DuckDB calculations and K1–K3 skills. Streamlit presents query-backed findings; optional Ollama/OpenAI can plan tools but cannot author displayed numbers. Load assessed: one Streamlit process, four simultaneous investigations on Windows.

Verdict: **hardened prototype suitable for controlled acceptance testing; not yet production-approved.**

## Must fix before production approval

1. **Broader real model behavior still requires verification.**
   - What this is: Model-based planning and provider fallback are optional integrations in providers.py / agent.py.
   - Current evidence: OpenAI inference, application Test Connection and the full August/September K1 browser workflow now succeed. The first real plan exposed incorrect month ends and duplicate task/chart handling; those failures were reproduced, corrected and regression-tested. Ollama remains unreachable. The main automated suite intentionally runs without live opt-in; manual live evidence is in reports/openai_live_validation.json.
   - Remaining work: Rotate the exposed server key, expand the live reference evaluation across enabled metrics/skills and failure paths, and configure an authorized Ollama model if needed. One successful real question is not a complete live-model accuracy evaluation.
   - If we skip it: A mocked integration pass could be mistaken for a working production model workflow.

2. **Real identity-provider behavior is unverified.**
   - What this is: access.py and ui.current_scope derive permissions from validated OIDC identities and a server-owned scope map.
   - Problem: No actual client/issuer has been registered or logged in. Private production mode intentionally denies access without configuration. The owner explicitly authorized a separate public synthetic demo; it cannot use providers or another warehouse. Claim availability and revocation vary by IdP.
   - Fix: Configure the secret template and test signed login/logout, iss/sub/exp claims, expired/revoked users, scope changes and restricted Explorer access with the actual IdP.
   - If we skip it: Approved users may be unable to sign in, or identity lifecycle behavior may differ from the simulated contract.

3. **Hosted reliability and operational limits are unverified.**
   - What this is: render.yaml uses the user-selected Free single-process service with 512 MB host RAM and a 320 MB DuckDB budget; paid resources are not authorized.
   - Current evidence: GitHub Linux CI verifies all 195 tests. The Free Render service is live, with root/health HTTP 200, a recorded restart and the expected login-configuration guard. Local Streamlit peaks at 422.12 MiB with the reduced budget. Hosted authenticated analytics memory and sustained capacity remain unverified.
   - Remaining work: Configure OIDC, test hosted authenticated workflows and representative load, establish monitoring and any separately authorized API spend limit, then assess against an agreed traffic/SLA target.
   - If we skip it: Local success may be mistaken for a reliable hosted service or a tested operating budget.

## Resolved audit findings

| Finding | Concrete failure reproduced | Correction and evidence |
|---|---|---|
| Wrong contribution dimension | Asking which services contributed selected markets | Approved service routing; regression |
| Ignored filters/date grain | Service Delta / unknown device / August 1 vs 2 executed another population | Unsupported/clarification response before queries |
| Wrong cohort intent | New versus existing became existing-user totals | MAU + K3; hand-calculated regression |
| Device adoption mismatch | Mid-period switch retained active numerator but lost denominator | Real temporal intersection; adoption v1.1 |
| Incomplete trend | Zero-activity days omitted; missing days could be mistaken for zeros | Full calendar and null gaps; visible provisional warnings |
| Misleading rate change | A 100% to 0% rate delta appeared as -100% rather than percentage points | Explicit pp and relative-percent units |
| Incomplete evidence | Custom day request retained only the original comparison periods | Actual executed period and scope metadata |
| Stale fallback metadata | Local fallback retained cloud model name; prior demo hid new fallback reason | Actual reply model, failure reason and latest status regressions |
| Lost primary findings | Model could select only a generic limitation | Computed change and completeness remain visible |
| Unsafe bad-source acceptance | Conflicting event IDs and impossible ingestion could pass deduplication | Withhold outputs; quality regressions |
| Aggregate query memory | Shared app could launch several 512MB queries together | Serialized sessions, deadline-aware queue and coalesced cache misses |
| Provider resource/error handling | Invalid model lists leaked raw exceptions | Classified safe errors and owned-client cleanup |
| Anonymous cloud-cost exposure | Public hosted app had no identity gate | Production defaults deny before controls; explicit server scopes |
| Stale imports / clipped cards | Earlier Settings exception and compact KPI ellipsis | Clean-restart policy and wrapping cards; browser proof |
| Installer vulnerabilities | Scan found two distinct pip advisories (four feed records) | pip 26.2.1; repeat scan has 0 records |

## Actual acceptance evidence

193 passed, 0 failed, 2 skipped of 195 tests on both Windows and GitHub Linux CI. Both the 30 independent calculations and 30 human-question deterministic workflows matched all references. Five EVP demos were actually executed. All displayed numerical findings in these workflows came from the shared skills and approved queries. A separate real OpenAI browser comparison also returned the independent MAU totals.

Measured cold investigation 7.196s, warm 5.683ms, four simultaneous investigations all passed, peak backend 385.04 MiB. Two real startup/restart checks passed. Desktop 1366x900 and normal compact browser layouts were inspected; production guard and revocation paths were exercised with simulated claims.

No source credential candidates were found in the local scan. The dependency scan checked 83 packages with 0 known findings and no skipped packages. These checks are not penetration testing, production security certification, live model evaluation or hosted capacity approval.

## Reproduce and review

Run python -m scripts.evaluate, scripts.validate_data, scripts.run_demos, scripts.benchmark, scripts.security_check and scripts.smoke_deployment --port 8765 using the project virtual-environment Python. For published advisories, install requirements-dev.txt and run python -m pip_audit --format json --output reports/dependencies_audit.json.

The .github/workflows/quality.yml actually passed tests, credential checks, advisories and restart smoke on Linux without live credentials. Run 38508157329 verifies application source commit 36e0c7c0c72279f4af713d8fb6519952ab2e8f32; see reports/github_validation.json and the repository Actions tab. Direct runtime packages are pinned; transitive dependencies are not fully locked and must be scanned in the target environment.

Evidence files are under reports/; FINAL_VALIDATION_REPORT.md summarizes actual measurements. DEPLOYMENT_GUIDE.md covers OIDC and Render setup. Streamlit's authentication protocol verifies identity; the application's scope map separately authorizes data access. See [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication). Render Secret Files are read from /etc/secrets/secrets.toml; see [Render documentation](https://render.com/docs/configure-environment-variables#secret-files).

Not checked: real enterprise data, broad live LLM accuracy, live Ollama, signed IdP login, hosted signed-in analytics and sustained production traffic, formal penetration testing or disaster-recovery operations. Source was published to the explicitly authorized public GitHub repository; Free application hosting is live; no paid resource creation or model downloads occurred.
