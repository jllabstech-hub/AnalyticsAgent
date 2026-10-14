"""Sales charts, approved SQL, and observable platform components."""
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from analytics_agent.exports import csv_report,excel_report,pdf_report


def trace_panel(answer):
    st.subheader("Component Functionality Trace")
    st.caption("Executed inputs, outputs and validation evidence. No hidden model reasoning.")
    st.dataframe(pd.DataFrame([{"Step":e.get("component_id"),"Component":e["stage"],"Status":e["status"],
        "Component duration ms":e.get("duration_ms"),"Time since start ms":e.get("elapsed_ms")} for e in answer.trace]),hide_index=True,width="stretch")
    for event in answer.trace:
        with st.expander(f"{event.get('component_id','')} · {event['stage']} · {event['status']}"):
            details={key:value for key,value in event.items() if key not in ("stage","status")}
            st.json(details)
    st.download_button("Download component trace JSON",answer.model_dump_json(indent=2),"component_trace.json","application/json",key="trace_json_download")


def downloads(answer):
    with st.expander("Download executed results"):
        st.caption("Exports contain executed values and source evidence; no new queries or LLM calls.")
        for label, builder, filename, mime in [("Download CSV",csv_report,"analytics_results.csv","text/csv"),
            ("Download Excel",excel_report,"analytics_results.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Download PDF",pdf_report,"analytics_report.pdf","application/pdf")]:
            st.download_button(label,builder(answer),filename,mime,key="export_"+filename)


def sales_panel(answer):
    st.caption("Domain: Sales Analytics | Provider "+("attempted: " if answer.status=="error" else "used: ")+answer.provider)
    if answer.status!="ok":
        (st.info if answer.status=="clarification" else st.warning)(answer.message)
        trace_panel(answer)
        return
    first=answer.results[0]; money=first.request.metric in ("net_sales","avg_order_value")
    def fmt(value): return "Undefined" if value is None else f"${value:,.2f}" if money else f"{value:,.0f}"
    if not first.quality["complete"]: st.warning("Provisional sales results: reporting coverage is incomplete. Partial months are labeled.")
    st.subheader(first.request.metric.replace("_"," ").title()+(" · USD" if money else ""))
    st.caption(f"UTC | {first.request.baseline.start} to {first.request.baseline.end} vs {first.request.current.start} to {first.request.current.end} | End dates exclusive")
    with st.container(horizontal=True,wrap=True,gap="small",key="sales_kpis"):
        st.metric("Baseline",fmt(first.baseline),border=True,width=280)
        st.metric("Current",fmt(first.current),border=True,width=280)
        st.metric("Absolute change",fmt(first.absolute_change),f"{first.percentage_change:+.2f}% relative" if first.percentage_change is not None else None,border=True,width=280)
    for result in answer.results:
        if result.trend:
            data=pd.DataFrame(result.trend)
            data["month_in_period"]=data.groupby("period").cumcount()+1
            chart=px.bar(data,x="month_in_period",y="value",color="period",barmode="group",hover_data=["month","units_sold","orders","coverage_complete"],
                color_discrete_map={"baseline":"#183B56","current":"#18A5A2"},title="Monthly comparison · Hover for actual calendar month")
            chart.update_layout(height=300,xaxis_title="Month within comparison period",yaxis_title="USD" if money else "Value",margin=dict(l=0,r=0,t=45,b=0))
            st.plotly_chart(chart,width="stretch",key="sales_trend")
            st.dataframe(data.drop(columns="month_in_period"),hide_index=True,width="stretch")
        if result.records:
            data=pd.DataFrame(result.records)
            chart=px.bar(data,x="group",y="change",color="change",color_continuous_scale=["#183B56","#18A5A2"],title="Observed sales group changes")
            chart.update_layout(height=280,coloraxis_showscale=False,xaxis_title="Group",yaxis_title="USD change" if money else "Change")
            st.plotly_chart(chart,width="stretch",key="sales_contribution")
            st.dataframe(data,hide_index=True,width="stretch")
            st.caption("Group changes reconcile to the total." if result.reconciliation.get("reconciled") else "Overlapping populations or ratios: group deltas cannot be summed.")
    st.subheader("Analytical findings")
    for finding in answer.findings: st.write(finding)
    with st.expander("Sales definitions, sources and quality"):
        st.json(answer.knowledge)
        st.json(first.quality)
        for warning in first.warnings: st.warning(warning)
    with st.expander("Approved SQL and bound parameters"):
        for query in first.queries:
            st.caption(query["template"]+" · "+query["period"])
            st.code(query["sql"],language="sql")
            st.json(query["parameters"])
        st.caption("Parameters are bound separately. Questions and models cannot supply SQL.")
    downloads(answer)
    trace_panel(answer)
