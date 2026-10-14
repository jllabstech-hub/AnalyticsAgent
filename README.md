# BDC Analytics Agent — Prototype V1

A working synthetic enterprise analytics prototype with a Streamlit workspace,
DuckDB, YAML metrics, K1–K3 skills, a bounded orchestrator, Ollama by default and
optional OpenAI. All accounts, users, markets, devices and services are fictional.

Repository: https://github.com/jllabstech-hub/AnalyticsAgent

Open http://localhost:8501 after startup. Explicitly enable **Deterministic demo
mode** in the sidebar to use the complete prototype without any LLM or API key.
Ollama remains the default; cloud processing requires explicit Settings selection.

The end-to-end audit hardened numerical output, concurrent execution and access.
See `PRODUCTION_READINESS.md` for current evidence and deployment blockers.
Local mode runs only on your own machine. `APP_ENV=production` (forced on Render)
requires OIDC sign-in and server-defined account scopes before analytics is shown.
OpenAI connection and one complete live MAU comparison have been verified locally.
Actual identity-provider login, Ollama inference, broader live model evaluation,
and hosted behavior remain unverified. See reports/openai_live_validation.json.

## Quick start — Windows PowerShell

Required: Python 3.11–3.14, PowerShell and a browser. This build was tested with
Python 3.14.5. Git is needed only for later repository/deployment work.

On a new machine, clone the repository first and run the commands from that
checkout. Change the working-directory example below to your checkout path.

```powershell
git clone https://github.com/jllabstech-hub/AnalyticsAgent.git
Set-Location AnalyticsAgent
```

```powershell
Set-Location 'D:\Office\AnalyticsAgent'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.2.1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The generated Parquet files are bundled already. To reproduce them and the
independent test fixtures:

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_data
.\.venv\Scripts\python.exe -m scripts.validate_data
.\.venv\Scripts\python.exe -m scripts.reference_answers
```

Stop with Ctrl+C. Restart after changing backend configuration classes; hot reload
may retain imported modules. Calling virtual-environment Python directly avoids
PowerShell activation-policy issues. Optional activation: `.\.venv\Scripts\Activate.ps1`.

## Workspace

- **Analytics Workspace:** conversation, suggested questions, computed KPIs,
  Plotly trends, contribution/cohort tables, findings, warnings and source evidence.
- **Agent Execution:** completed skills and validation sequence, without hidden reasoning.
- **Settings:** provider/model selection, explicit cloud choice, connection test,
  fallback preference, actual provider status and last fallback reason.
- **Data Explorer:** approved read-only schemas, row counts and fictional samples.
- **Evaluation Dashboard:** measured automated results and known limitations.

Start with **Compare August and September active users.** Then ask **Which markets
contributed most to the decline?** See `DEMO_GUIDE.md` for five complete scenarios.
Questions for unavailable business data produce a limitation; ambiguous questions
request clarification. All six supported metrics and definitions are in
`analytics_agent/metrics.yaml`.

## Synthetic warehouse

| Dataset | Purpose |
|---|---|
| users | 100,000 fictional accounts, registration and activation dates |
| service_activity | Usage events, timestamps, duplicate IDs and delayed ingestion |
| service_membership | Eligibility periods and fictional Standard/Premium cohorts |
| device_mapping | Time-valid associations and device changes |
| market_reference | Market A–E and UTC semantics |
| data_quality_status | Completeness, reporting coverage and historical freshness |

Default seed is 20260701. Events cover July–September 2026. The primary August/
September comparison is complete; `data/synthetic/incomplete/` is a separately
identified September quality scenario. Exact row/event counts and injected issues
are in `data/synthetic/validation_report.json`. Independent pandas answers are
stored only in `tests/fixtures/`; no agent module reads them.

Distinct populations are unioned, not added. Ratio and overlapping-group
contributions do not reconcile as additive totals. The supporting trend chart
is explicitly DAU, including when the comparison metric differs. Freshness uses
an October 5 synthetic snapshot, not live enterprise data.

## Ollama — default local provider

Install manually from [the official Windows installer](https://ollama.com/download/windows)
after choosing to do so. The build has not installed software or downloaded models.
If Ollama is not already running, start it in another terminal:

```powershell
ollama serve
```

Only after authorizing the download yourself, choose a model:

```powershell
ollama pull qwen3:8b
# Smaller alternative; choose this instead on limited hardware:
ollama pull qwen3:1.7b
```

Set `OLLAMA_MODEL=qwen3:1.7b` in `.env`, or select it in Settings after installation.
The detected MX330 has 2 GiB VRAM; the 8B model will not fit wholly in that GPU,
and CPU offload may be slow. The smaller model is an option, not a promise of
verified GPU acceleration. Verify the installed model and actual inference:

```powershell
ollama list
nvidia-smi
.\.venv\Scripts\python.exe -m scripts.diagnose_llm --inference
```

The current live diagnostic reports Ollama unreachable. Mocked tests pass, but
successful live inference and GPU offload have not been verified. A remote
endpoint requires HTTPS plus `OLLAMA_API_TOKEN` for an authenticated proxy.
Render cannot reach localhost on your Windows laptop.

## Optional OpenAI

Set `OPENAI_API_KEY` on the server (local `.env` or Render environment variables)
and configure `OPENAI_MODEL=gpt-4.1-mini`. Then explicitly select **OpenAI API**
in Settings. The model selector also accepts a user-entered model supporting
Chat Completions and function calling. No browser key field is provided; credentials
never enter session state or logs. API account usage may incur charges.

Missing key, timeout, connection or temporary service failure can fall back to
Ollama only if enabled, reachable and the selected model is available.
Authentication errors and invalid requests do not fall back. Ollama never
selects OpenAI automatically; fallback remains local for the rest of an answer.
Passive startup and status inspection do not call OpenAI. Live OpenAI is unverified
and no cloud inference was initiated during this build.

## Tests and measured evidence

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate
.\.venv\Scripts\python.exe -m scripts.run_demos
.\.venv\Scripts\python.exe -m scripts.benchmark
.\.venv\Scripts\python.exe -m scripts.security_check
.\.venv\Scripts\python.exe -m scripts.smoke_deployment --port 8765
```

`reports/evaluation.json` and `reports/test_results.xml` are generated from real
Pytest results. Live tests are explicitly gated: set `RUN_LIVE_OLLAMA=1` only when
local inference is ready; set `RUN_LIVE_OPENAI=1` only when cloud testing is authorized.
Do not treat synthetic-suite accuracy as enterprise production readiness.

See `FINAL_VALIDATION_REPORT.md` for final counts, performance, security review
and external blockers; `BUILD_LOG.md` records commands, failures and fixes.

## Deployment

`render.yaml` binds to `$PORT` on `0.0.0.0`, reads bundled Parquet and requires no
persistent disk. The selected Render plan is Free, with a 320 MB DuckDB budget,
100-row result limit and 180-second investigation deadline. Free hosting is
authorized; paid resources are not. Production login must be configured before
analytics is accessible. Free services sleep on idle and have usage quotas.
Use `DEPLOYMENT_GUIDE.md` for exact Git and Render steps and local restart checks.

## Project files

```text
app.py
analytics_agent/  config, models, engine, semantics, metrics.yaml, skills, providers, agent, ui
scripts/          generate_data, validate_data, reference_answers, diagnose_llm,
                  evaluate, run_demos, benchmark, security_check, smoke_deployment, start.ps1
data/synthetic/   six Parquet datasets, manifest, validation report, incomplete partition
tests/            independent fixtures and module/integration/UI tests
reports/          real evaluation, demo, performance, diagnostics and startup evidence
.streamlit/       theme
render.yaml       reviewed deployment specification
.env.example      safe template; .env remains ignored
```

Dependencies are directly pinned; they are not a full transitive lockfile.
Frontend, analytical backend and providers are separate. The application uses
no LangGraph, vector database, microservices or multi-agent framework.

## Troubleshooting

- **Python or py unavailable:** install Python 3.11–3.14, reopen PowerShell, and
  check `python --version`. This machine uses `python`, not the `py` launcher.
- **Missing modules:** install and run using the same `.venv\Scripts\python.exe`.
- **Port busy:** stop the earlier server or add `--server.port 8502` and open that port.
- **Ollama unavailable:** test Settings, verify `ollama list`, or explicitly select demo mode.
- **OpenAI failure:** check server configuration and Settings; authentication errors
  require fixing credentials, rather than automatic fallback.
- **Memory failure:** 256 MB DuckDB was insufficient for full-warehouse validation.
  Use the tested 512 MB budget and allow additional Python/Streamlit memory.
- **Stale imported settings after code changes:** stop and restart Streamlit.
- **Dataset issues:** run `scripts.validate_data` and inspect its error before analysis.

Known limits: historical synthetic data only; a bounded demo parser; governed
explanation templates; actual OIDC login, Ollama and broader live model behavior remain unverified;
Linux/Render hosting and expected production traffic require separate verification.

References: [Ollama Windows](https://docs.ollama.com/windows),
[Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling),
[OpenAI GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[DuckDB security](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview),
[Streamlit widget persistence](https://docs.streamlit.io/develop/concepts/architecture/widget-behavior),
[Render service configuration](https://render.com/docs/web-services).
