# Deployment guide

The user authorized Render deployment and selected the Free compute plan on
14 October 2026. The Blueprint uses Free only, with no paid disk or autoscaling.
Production login configuration remains required before analytics can be opened.

## Windows setup

```powershell
Set-Location 'D:\Office\AnalyticsAgent'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.2.1
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m scripts.generate_data
.\.venv\Scripts\python.exe -m scripts.validate_data
.\.venv\Scripts\python.exe -m scripts.reference_answers
.\.venv\Scripts\python.exe -m scripts.evaluate
.\scripts\start.ps1
```

If script execution is blocked, run
`.\.venv\Scripts\python.exe -m streamlit run app.py` directly.
Stop an existing server with Ctrl+C before restarting. Restart after modifying
backend configuration classes; hot reload can retain older imported modules.

## GitHub instructions

The selected repository is https://github.com/jllabstech-hub/AnalyticsAgent.
GitHub source upload and free Render deployment are authorized. For a new checkout:

```powershell
git clone https://github.com/jllabstech-hub/AnalyticsAgent.git
Set-Location AnalyticsAgent
```

For later updates, review `git diff`, stage the intended files, inspect
`git diff --cached --stat`, commit, and push to `main`. `.env`, actual OIDC secrets,
virtual environments, local model/install artifacts, rendering intermediates,
logs and local database files are ignored. Synthetic Parquet and test-only
reference fixtures are bundled. The agent does not import evaluation fixtures.

## Render Web Service

Connect the public repository,
choose **New → Web Service**, select Python, and configure the following. A
Blueprint with the same settings is supplied in `render.yaml`. Auto-deploy is off.

- Build: `python -m pip install --upgrade pip==26.2.1 && python -m pip install --prefer-binary -r requirements.txt`
- Start: `streamlit run app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true`
- Health: `/_stcore/health`
- Python: `PYTHON_VERSION=3.14.5`
- Region: Singapore (`singapore`)
- DuckDB: `DUCKDB_MEMORY_LIMIT=320MB`; one thread, no disk spill.
- Results: `RESULT_LIMIT=100`; investigation deadline `INVESTIGATION_TIMEOUT_SECONDS=180`.
- Selected plan: `free` (0.1 CPU, 512 MB RAM, US$0/month compute).

The 256 MB DuckDB budget failed full-warehouse join validation. A 320 MB budget
passes the three-skill investigation and its Streamlit test, which peaks at 422.12
MiB on Windows. This does not certify hosted memory or concurrent traffic; verify
again after sign-in is configured. No persistent disk is needed. The Free service
sleeps after 15 idle minutes and has monthly instance-hour, bandwidth and build
quotas. Do not upgrade or add paid resources. Without a payment method, exhausted
quotas suspend service/builds; with a payment method, overage billing can apply.
See [Render Free limits](https://render.com/docs/free) and review account usage.

Put API keys only in Render environment variables. Default provider is Ollama;
OLLAMA_BASE_URL is deliberately empty in the hosted configuration until a secured
reachable endpoint is supplied. The Windows laptop's localhost is unreachable from Render. Use explicit demo
mode when no provider is reachable, or select configured OpenAI in Settings.

For OpenAI set `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4.1-mini`, and choose OpenAI.
API account usage can incur charges; passive status checks do not make cloud calls.
For remote Ollama, set `OLLAMA_BASE_URL` to an independently hosted HTTPS origin
and `OLLAMA_API_TOKEN` for a proxy that actually enforces bearer authentication.
Do not expose port 11434 publicly. Local processing never selects OpenAI silently.
Production access requires the OIDC configuration below, which remains unverified with a real identity provider.

## Required production sign-in

`APP_ENV=production` is set by the Blueprint; Render also forces it automatically.
The app stops before analytics or provider calls until OIDC and an explicit access
map are configured. Local demos retain `APP_ENV=local` and bind to localhost.
Do not expose local mode as a public service with an API key.

1. Register an OIDC client with your approved identity provider. Configure the exact
   HTTPS callback `https://YOUR_SERVICE.onrender.com/oauth2callback`.
2. Use `.streamlit/secrets.example.toml` as a template. Replace every placeholder
   with your actual client ID/secret, HTTPS metadata URL and a random cookie secret
   of at least 32 characters. Authlib is included in the pinned requirements.
3. Add each approved principal to `[access."ISSUER|SUBJECT"]` with explicit
   `markets`, `services` and `skills`. These values come from a verified identity
   token, never from email text or an analytical question. The identity must expose
   `iss`, `sub` and `exp`; missing/expired claims deny access. This provider-specific
   claims contract must be tested against your IdP before deployment approval.
4. In Render **Environment → Secret Files**, create `secrets.toml` with those
   contents. Streamlit reads `/etc/secrets/secrets.toml`; no persistent disk is needed.
   For controlled local sign-in testing use ignored `.streamlit/secrets.toml` and
   an approved HTTPS development callback. Never commit either secret file.
5. Verify approved, unapproved, expired and revoked accounts; test a principal with
   only Market A / Service Alpha access. Changes in effective scopes clear retained
   answers and conversation. Data Explorer requires full market/service access.

The guard is tested with simulated claims and UI flows. Actual client registration,
login, logout, token expiry and IdP revocation have not been live-tested. OIDC verifies
identity; the app separately applies account authorization. Monitor authenticated
API use and enforce an account-level spend cap before enabling cloud use. The local
four-request benchmark is not a production traffic or abuse test.

References: [Streamlit authentication](https://docs.streamlit.io/develop/concepts/connections/authentication),
[Render Secret Files](https://render.com/docs/configure-environment-variables#secret-files).

## Local deployment-equivalent test

```powershell
.\.venv\Scripts\python.exe -m scripts.smoke_deployment --port 8765
.\.venv\Scripts\python.exe -m scripts.benchmark
```

The smoke command starts twice with the Render address and assigned port,
verifies real HTTP health, and stops its own process trees. This is a Windows
startup test, not a hosted Render deployment. After authorized deployment,
verify hosted health, run all five demos, restart the service and repeat the KPI
comparison. Linux/cloud hosting remains unverified until that happens.

References: [Render port binding](https://render.com/docs/web-services),
[Python versions](https://render.com/docs/python-version),
[compute plans](https://render.com/docs/compute-plans).
