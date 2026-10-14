# Synthetic analytics pipeline and component trace

Two registered domain packs run in the same platform: existing account/service
usage and new fictional sales. The seven-stage sales workflow follows the supplied
architecture diagram. All businesses, products, markets, orders and identifiers
are fictional. Real enterprise databases and messaging channels are not connected.

Try: **Show Orion One sales performance in Market A for Q3 2026 compared with Q2 2026.**
Select Sales Analytics under Suggested domain, or type a question containing sales,
revenue, units sold, orders or average order value. The question routes automatically.

| Component | Actual functionality | Source | Independent verification |
|---|---|---|---|
| 1 User Query | Size/credential validation, mode policy, no secret capture in trace | platform.py | refusal and public provider tests |
| 2 Intent Understanding | Resolve metric, product, market, channel and UTC periods; clarify unsupported/ambiguous input | sales_parser.py | routing, unknown-filter and period tests |
| 3 Domain & Skill Selection | Read versioned registry; choose Sales Analytics S1 comparison/S2 contribution; enforce domain and operation grants | domains.yaml, sales_skills.py | domain scope/skill allowlist tests |
| 4 Knowledge Retrieval | Load metric meaning, joins and source catalog; execute DESCRIBE for actual Parquet view schemas | sales_metrics.yaml, sales_engine.py | source/schema and metric-contract assertions |
| 5 Approved Query Generation | Generate allowlisted SQL with placeholders; keep parameters separate; optionally validate provider tool output against the approved question | sales_engine.py, platform.py | altered SQL/binding/scope denial and mocked provider tests |
| 6 Execute & Validate | Deduplicate line IDs; integer-cent arithmetic; FK/PK cardinality, order grain, denominator, coverage/freshness and numeric reconciliation | sales_engine.py, sales_skills.py | 40 independent pandas references plus damaged-data/overlap/zero/incomplete tests |
| 7 Results & Insights | Query-backed KPIs, monthly charts, group tables, computed findings, follow-ups, CSV/Excel/PDF and trace JSON | platform_ui.py, exports.py | real Streamlit AppTest, export reopening and rendered PDF review |

Open **Agent Execution** for the component table and expandable inputs/outputs.
The sales result panel also shows approved SQL and bound parameters. Component
duration and time since start come from actual execution clocks. These events
describe actions and results; they do not disclose hidden model reasoning.

## Synthetic sales data

- 25,000 orders and 50,000 canonical order lines; 50,500 physical rows include 500 retransmissions.
- Four fictional products, five fictional markets and three fictional channels.
- April 1 through September 30, 2026; Q2 baseline and Q3 current period are complete.
- USD cents stored as integers; net sales subtract discounts and returns and add signed adjustments.
- Units sold means gross invoiced units. Orders are distinct and can overlap across product groups.
- A separately identified incomplete partition omits September 24-30.
- Reproducible seed 20260401. Relative "last three months" means the last complete dataset quarter, anchored to October 1, 2026.

Generate and independently validate:

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_sales_data
.\.venv\Scripts\python.exe -m scripts.sales_reference
.\.venv\Scripts\python.exe -m scripts.trace_pipeline
.\.venv\Scripts\python.exe -m scripts.evaluate
```

Reference answers are under tests/fixtures and are never imported by runtime agents.
Execution traces are generated independently by scripts.trace_pipeline and saved
under reports. UI exports run in memory and require no persistent Render storage.

## Access and extensions

Public Free mode accepts only the two bundled synthetic warehouses and blocks all
LLM providers. Local/private mode retains Ollama/OpenAI selection. Private grants
default to usage only; sales requires `domains = ["usage", "sales"]` in the approved
server principal scope. Existing grants are not silently expanded. Market and K1/K2
operation restrictions also apply to sales. Domain switches clear incompatible
period/filter context. One process-wide warehouse lock serializes both adapters
within the Free memory budget.

A new domain needs its own validated request contract, source adapter, semantic
definitions, approved operations and independent reference tests, followed by a
registry entry. Unsupported domains and cross-domain joins are clarified rather
than producing invented results. Actual enterprise connectors, Teams/Slack/email,
real identity lifecycle and sustained production load remain separate integrations.
