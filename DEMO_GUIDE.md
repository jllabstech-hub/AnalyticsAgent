# EVP demonstration guide

Five workflows are taken from the complete scenarios in Phase 12, which fill
the truncated Phase 11 prompt. All findings are computed, not scripted answers.

## Before the demonstration

Run Streamlit and open http://localhost:8501. Label the session as synthetic.
Ollama is the default provider; use Settings to test a configured model. On this
machine live Ollama is unavailable. Explicitly enable **Deterministic demo mode**
in the sidebar for a complete demonstration without a model or API key. Keep
the five scenarios in order to demonstrate authorized follow-up context.

## Demo 1 — KPI comparison

Ask: **Compare August and September active users.**

Show K1, baseline/current cards, absolute and relative change, daily engagement
trend and the MAU definition. The overall count unions service populations;
it does not add overlapping service counts. End dates are exclusive and UTC.

## Demo 2 — Automatic market contributions

Ask: **Which markets contributed most to the decline?**

Show K2 and the inherited MAU/period context. Display all market deltas, including
positive offsets, and the reconciliation against the overall change. A share
can exceed 100% when growth elsewhere offsets decline. Market A is an observed
contributor, not a proven business root cause. Open the query evidence.

## Demo 3 — Multi-step investigation

Ask: **Investigate the September decline across markets and cohorts.**

Show K1 → K2 → K3 in the execution trace, market and cohort tables, and the
consolidated findings. Explain that new/existing membership is defined at each
period start, so this is not a fixed-cohort retention study. The display keeps
observations, contribution and causal hypotheses distinct; it claims no cause.

## Demo 4 — Data-quality detection

Ask: **Can we trust the September activity data?**

Show completeness, historical snapshot freshness, duplicate removal, delayed
ingestion, and passed join-cardinality checks. The primary August/September
comparison is complete and includes late arrivals. Then optionally ask
**Can we trust the September activity data in the incomplete scenario?**
Show the incomplete-period warning; do not interpret that scenario's decline as
a business cause. Return to the primary scenario or clear the conversation.

## Demo 5 — Conversational follow-up

Ask: **Now compare only Market A for the same periods.**

Show the inherited periods, applied market filter and newly calculated KPIs.
Changing provider in Settings preserves the authorized analytical context,
but unavailable LLMs do not generate an answer. Demo mode remains explicit.

## Reproduce and evidence

```powershell
Set-Location 'D:\Office\AnalyticsAgent'
.\.venv\Scripts\python.exe -m scripts.run_demos
.\.venv\Scripts\python.exe -m pytest tests/test_demo_workflows.py -q
```

`reports/demo_results.json` contains actual results, warnings, skill/query
versions, executed templates, latency and evidence for the five workflows.
The tests compare key results against separate pandas reference fixtures.
Neither fixtures nor expected answers are passed into the agent.

Contribution percentages use the net total change as their denominator. They can exceed 100% or be negative when growth in other groups offsets a decline. For the executed primary MAU investigation, Market A -4506 plus the other four market changes (+3773) reconciles to -733. This is observed arithmetic, not a confirmed cause. New/existing cohorts are period-relative; their changes (-484 and -249) also reconcile to -733.
