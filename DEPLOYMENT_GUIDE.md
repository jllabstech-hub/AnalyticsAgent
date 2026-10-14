# Deployment guide

No paid resource or public service has been created. Applying the prepared
Blueprint creates a paid public Web Service and requires authorization first.

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
GitHub source upload is authorized; paid/public application hosting still requires
separate authorization. For a new checkout:

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

After authorizing hosting and the resource plan, connect the private repository,
choose **New → Web Service**, select Python, and configure the following. A
Blueprint with the same settings is supplied in `render.yaml`. Auto-deploy is off.

- Build: `python -m pip install --upgrade pip==26.2.1 && python -m pip install --prefer-binary -r requirements.txt`
- Start: `streamlit run app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true`
- Health: `/_stcore/health`
- Python: `PYTHON_VERSION=3.14.5`
- DuckDB: `DUCKDB_MEMORY_LIMIT=512MB`; one thread, no disk spill.
- Prepared plan: `1c-2g` (2 GB RAM). This is a paid configuration, not an approved purchase.

The 256 MB DuckDB budget failed full-warehouse join validation. Do not assume
Render's 512 MB free instance can accommodate both DuckDB and Streamlit. See
`reports/performance.json` for measured Windows memory and latency. The 2 GB
configuration provides headroom for a small demonstration; concurrency and Linux
memory behavior still need hosted verification. No persistent disk is needed.

Put API keys only in Render environment variables. Default provider is Ollama;
the Windows laptop's localhost is unreachable from Render. Use explicit demo
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
