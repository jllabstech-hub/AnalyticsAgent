# Four-domain synthetic analytics platform

The same Streamlit workspace routes four registered domains. Each uses approved
typed requests, read-only parameterized DuckDB queries, metadata retrieval,
quality validation, query-backed findings and seven observable component events.
All records, users, products, markets, campaigns and departments are fictional.

| Domain | Synthetic data | Registered metrics | Operations |
|---|---|---|---|
| Account/Service Usage | 100,000 users; July–September 2026 | MAU, DAU, New Users, Active Existing Users, Activation Rate, Adoption Rate | K1 comparison, K2 contribution, K3 cohorts |
| Sales | 25,000 orders; 50,000 canonical lines; April–September 2026 | Net Sales, Units Sold, Orders, Average Order Value | S1 comparison, S2 contribution |
| Marketing | 60,000 canonical impression observations; April–September 2026 | Impressions, Clicks, Conversions, Marketing Spend, CTR, Conversion Rate, Cost per Click | M1 comparison, M2 contribution |
| Finance | 30,000 canonical booked transactions; April–September 2026 | Booked Revenue, Expenses, Modeled Profit, Profit Margin | F1 comparison, F2 contribution |

Select **Suggested domain** and use one of its five questions. Typed questions also
route automatically. Open **Agent Execution** to inspect actual inputs, outputs,
SQL bindings, source schemas, quality checks and component durations. **Data
Explorer** provides each domain's source schemas, physical row counts and samples.
CSV, Excel, PDF and complete trace JSON downloads contain executed results.

The four-domain release is live at the [Free Render app](https://bdc-analytics-agent-prototype.onrender.com)
on the existing Free service. No sign-in or API key is needed for public synthetic
analytics. The public Settings cannot enable providers. Free cold starts and the
large Usage calculation can take longer than the smaller business domains.

## Example questions

- Usage: "Compare August and September active users."
- Sales: "Show Orion One sales performance in Market A for Q3 2026 compared with Q2 2026."
- Marketing: "Compare marketing click through rate in Q3 versus Q2 2026."
- Marketing: "Which campaigns contributed to the change in marketing conversions in Q3 versus Q2 2026?"
- Marketing: "Investigate marketing spend across channels in Q3 compared with Q2 2026."
- Finance: "Compare finance profit in Q3 versus Q2 2026."
- Finance: "Which departments contributed to the change in finance expenses in Q3 versus Q2 2026?"
- Finance: "Investigate finance profit across categories in Q3 compared with Q2 2026."

Each domain also supports the documented August/September comparison and a
contextual campaign/department follow-up. Domain switches clear incompatible
requests. Mixed-domain joins and comparisons require clarification; they are not
registered analytical operations. Generic revenue follows Finance in an existing
Finance conversation and otherwise retains the established Sales interpretation.
Use "finance revenue" or "net sales" to make the intended source explicit.

## Population and numerical meaning

Marketing counts observations rather than unique people. Each canonical event
has one impression, zero/one click and zero/one conversion; conversion requires
a click. CTR is total clicks/total impressions. Conversion rate is total
conversions/total clicks. CPC is total allocated USD spend/total clicks. These
ratios use the same selected population and are not averages of group rates.

Finance is an analytical booked revenue/expense simulation. Revenue and expense
events have exclusive categories. Modeled profit is revenue minus cost of goods
and operating expenses. Margin is total modeled profit/total booked revenue.
This is not a double-entry general ledger or audited net income; tax, financing,
FX, balance sheets and cash flows are outside the source model. Finance booked
revenue and Sales invoiced net sales are separate populations and are not reconciled.

Money is integer USD cents before final presentation. Zero denominators produce
undefined values. Percentage-point changes are displayed for rates/margins.
Relative growth is undefined for a zero or negative baseline. Exclusive additive
groups reconcile; ratio group deltas are never summed. Findings describe observed
changes and contributions, with no unverified root-cause claims.

New generators use seeds 20260402 and 20260403. Marketing has 600 physical
retransmissions and 3,095 canonical late observations; Finance has 300
retransmissions and 1,465 late transactions. Deduplication uses the first arrival,
so late retransmissions cannot reclassify on-time observations. PK/FK, integer
schema, entity validity intervals, calendar dates, arrival ordering, populations
and numerator/denominator constraints validate before findings.

Primary Q2/Q3 data are complete. Separate incomplete partitions omit September
24–30. Coverage and snapshot freshness are reported explicitly; historical
snapshot freshness is assessed against October 10 rather than represented as live.

## Reproduce and test

```powershell
.\.venv\Scripts\python.exe -m scripts.generate_business_data
.\.venv\Scripts\python.exe -m scripts.business_reference
.\.venv\Scripts\python.exe -m scripts.trace_domains
.\.venv\Scripts\python.exe -m scripts.benchmark_domains
.\.venv\Scripts\python.exe -m scripts.evaluate
```

The pandas oracle computes 55 new independent metric/filter cases. Runtime
agents never import reference answers. Actual traces for all twenty documented
workflows are in reports/four_domain_pipeline_trace.json. Existing Usage and
Sales references and behaviors are preserved.

Final Windows and Linux CI: 459 passed, zero failed, two optional live-provider
skips of 461. The defined suite matches 125 independent calculations and 125
natural-language questions. All ten new-domain hosted demonstrations pass;
107 independent numerical comparisons cover their totals, trends and groups.
An actual hosted restart preserves reference comparisons across all four domains.
See reports/four_domain_hosted_verification.json for actual source and evidence.

To trace a component, run a suggested question, select **Agent Execution**, and
expand the numbered component. It records executed inputs, validated domain and
skill selection, retrieved schemas/definitions, approved SQL and bindings,
quality/reconciliation checks, query-backed findings and elapsed time. Download
the complete JSON to inspect the same evidence outside the application. This
trace displays component functionality and outputs, without hidden model reasoning.

## Access and hosting

Public Free mode permits only the four fixed bundled synthetic warehouses and
blocks all LLM calls. Local/private mode retains explicit Ollama/OpenAI selection;
new-domain planning uses validated plan_marketing/plan_finance tool contracts.
Actual new-domain LLM inference is not claimed from mocked tests.

Private grants still default to Usage only. Add marketing or finance explicitly
to the server-owned principal domains list. K1 grants comparison capability;
K2 grants contribution capability within approved domains and markets. Do not
copy credentials into browser state, source, public reports or Render demo settings.

All adapters share one process-wide warehouse execution lock and 320MB hosted
DuckDB budget. Queries do not need persistent storage. Measured single-process
Windows UI/export peak is 423.57 MiB; this does not certify hosted concurrency
or sustained load. No paid resource upgrade is required for this synthetic demo.
Real enterprise connectors, actual identity lifecycle and broader live-provider
accuracy require separate implementation or verification.
