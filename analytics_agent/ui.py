"""Streamlit presentation; numerical work stays in the frontend-independent backend."""
import json
import hashlib
import pandas as pd
import plotly.express as px
import streamlit as st
from analytics_agent.agent import AnalyticsAgent, ConversationContext, DEMOS
from analytics_agent.config import PROJECT_ROOT, load_settings
from analytics_agent.engine import Engine, TABLES
from analytics_agent.providers import ProviderError, manager_from_settings
from analytics_agent.skills import SkillRegistry
from analytics_agent.models import AccessScope
from analytics_agent.access import scope_for_claims, valid_auth_configuration
from analytics_agent.platform import PlatformAgent,PlatformContext,domain_registry
from analytics_agent.sales_engine import SalesEngine,SALES_TABLES
from analytics_agent.sales_parser import SALES_DEMOS
from analytics_agent.sales_skills import SalesSkills
from analytics_agent.platform_ui import sales_panel,trace_panel,downloads


def current_scope(settings):
    if settings.public_demo_enabled:
        if st.session_state.get("access_fingerprint") != "public_synthetic_demo":
            for key in ("last_answer", "context", "messages", "connection_status", "last_fallback_reason", "suggested_domain", "explorer_domain"):
                st.session_state.pop(key, None)
            st.session_state.access_fingerprint = "public_synthetic_demo"
        return AccessScope(domains=("usage","sales"))
    if settings.app_env != "production": return AccessScope(domains=("usage","sales"))
    try:
        auth = st.secrets["auth"].to_dict()
        access = st.secrets["access"].to_dict()
        if not valid_auth_configuration(auth) or not access: raise ValueError("Missing sign-in configuration")
    except Exception:
        st.error("Production access is disabled until server sign-in and approved account scopes are configured. See the deployment guide.")
        st.stop()
    if not st.user.is_logged_in:
        st.info("Sign in with your approved account to access analytics.")
        st.button("Sign in",on_click=st.login)
        st.stop()
    try: scope = scope_for_claims(st.user,access)
    except PermissionError as error:
        st.error(str(error))
        st.button("Sign out",on_click=st.logout)
        st.stop()
    fingerprint = hashlib.sha256(json.dumps([st.user.get("iss"),st.user.get("sub"),scope.model_dump(mode="json")],sort_keys=True).encode()).hexdigest()
    if st.session_state.get("access_fingerprint") != fingerprint:
        for key in ("last_answer","context","messages","suggested_domain","explorer_domain"): st.session_state.pop(key,None)
        st.session_state.access_fingerprint = fingerprint
    with st.sidebar: st.button("Sign out",on_click=st.logout)
    return scope


@st.cache_resource
def analytical_engine(result_limit):
    # Bounded scope-keyed result cache only; no connection or credentials shared.
    import os
    return Engine(result_limit=result_limit, memory=os.getenv("DUCKDB_MEMORY_LIMIT", "512MB"))


@st.cache_resource
def sales_engine(result_limit):
    import os
    return SalesEngine(result_limit=result_limit,memory=os.getenv("DUCKDB_MEMORY_LIMIT","320MB"))


def results_panel(answer):
    if getattr(answer,"domain",None)=="sales":
        sales_panel(answer)
        return
    st.caption(f"Provider {'attempted' if answer.status == 'error' else 'used'}: {answer.provider}" + (f" · Model: {answer.model}" if answer.model else ""))
    if answer.fallback_reason: st.warning(f"Fallback to Ollama: {answer.fallback_reason}")
    if answer.status != "ok":
        (st.info if answer.status == "clarification" else st.warning)(answer.message)
        return
    primary = answer.results[0]
    if not primary.quality.get("complete",True):
        st.warning("Provisional results: reporting coverage is incomplete or unverified. Missing chart days are gaps, not zero activity.")
    rate = primary.request.metric.endswith("rate")
    def value(number):
        if number is None: return "Undefined"
        return f"{number:.2%}" if rate else f"{number:,.2f}".rstrip("0").rstrip(".")
    st.subheader(primary.request.metric.replace("_", " ").upper())
    st.caption(f"UTC · {primary.request.baseline.start} to {primary.request.baseline.end} versus {primary.request.current.start} to {primary.request.current.end} · End dates exclusive")
    absolute = f"{primary.absolute_change*100:+.2f} pp" if rate and primary.absolute_change is not None else value(primary.absolute_change)
    with st.container(horizontal=True,wrap=True,gap="small"):
        st.metric("Baseline",value(primary.baseline),border=True,width=180)
        st.metric("Current",value(primary.current),border=True,width=180)
        st.metric("Absolute change",absolute,f"{primary.percentage_change:+.2f}% relative" if primary.percentage_change is not None else None,border=True,width=220)
    for index, result in enumerate(answer.results):
        if result.trend:
            chart = px.line(pd.DataFrame(result.trend), x="activity_day", y="active_users", title="Daily active users · Supporting engagement trend", color_discrete_sequence=["#007F86"])
            chart.update_layout(height=280, margin=dict(l=0,r=0,t=45,b=0), xaxis_title="UTC date", yaxis_title="Distinct users", paper_bgcolor="white", plot_bgcolor="white")
            st.plotly_chart(chart, width="stretch", key=f"trend_{index}_{result.skill}")
        if result.records:
            st.subheader(SkillRegistry.names[result.skill])
            data = pd.DataFrame(result.records)
            if rate:
                for column in ("baseline","current","change"): data[column] = data[column]*100
            chart = px.bar(data, x="group", y="change", color="change", color_continuous_scale=["#183B56", "#18A5A2"], title="Observed group changes")
            chart.update_layout(height=280, margin=dict(l=0,r=0,t=45,b=0), xaxis_title="Group", yaxis_title="Change (percentage points)" if rate else "Change (users)", coloraxis_showscale=False)
            st.plotly_chart(chart, width="stretch", key=f"groups_{index}_{result.skill}")
            st.dataframe(data, hide_index=True, width="stretch", key=f"groups_table_{index}_{result.skill}")
            if rate: st.caption("Baseline/current are percentages; change is percentage points; percentage_change is relative percent.")
            st.caption("Group deltas reconcile to the total." if result.reconciliation.get("reconciled") else "Group deltas cannot be summed: overlapping populations or a non-additive ratio.")
    st.subheader("Findings")
    for finding in answer.findings: st.write(finding)
    warnings = list(dict.fromkeys(w for result in answer.results for w in result.warnings))
    with st.expander("Data quality and limitations", expanded=not primary.quality.get("complete",True)):
        for warning in warnings: st.warning(warning)
        st.caption(primary.quality["freshness_basis"] + "; these are historical synthetic data.")
        st.json(primary.quality["events"])
    with st.expander("Evidence, definitions and sources"):
        st.write(primary.definition["business_meaning"])
        st.json(primary.definition)
        st.dataframe(pd.DataFrame([e.model_dump(mode="json") for result in answer.results for e in result.evidence]), hide_index=True, width="stretch")
    with st.expander("Execution trace"):
        st.caption(f"{answer.tool_calls} approved skill calls · {answer.elapsed_ms/1000:.2f} seconds")
        st.json(answer.trace)
    if hasattr(answer,"domain"):
        downloads(answer)
        with st.expander("Platform component functionality"):
            trace_panel(answer)


def save_preference(name):
    st.session_state[name] = st.session_state["_" + name]
    st.session_state.pop("connection_status", None)


def settings_panel(settings):
    if settings.public_demo_enabled:
        st.info("Provider settings are disabled in the public synthetic demo. No LLM connections are used.")
        return
    st.subheader("Settings")
    for name in ("selected_provider","ollama_model","openai_model","automatic_fallback"):
        st.session_state["_" + name] = st.session_state[name]
    st.radio("LLM provider", ["ollama", "openai"], format_func=lambda p: "Ollama Local" if p == "ollama" else "OpenAI API", key="_selected_provider", horizontal=True, on_change=save_preference, args=("selected_provider",))
    models = list(dict.fromkeys([st.session_state.ollama_model, settings.ollama_model, "qwen3:8b", "qwen3:1.7b"] + st.session_state.get("ollama_models", [])))
    st.selectbox("Ollama model", models, key="_ollama_model", on_change=save_preference, args=("ollama_model",))
    st.selectbox("OpenAI model", list(dict.fromkeys([st.session_state.openai_model,settings.openai_model,"gpt-4.1-mini"])), accept_new_options=True, key="_openai_model", on_change=save_preference, args=("openai_model",))
    st.toggle("Automatic OpenAI-to-Ollama fallback", key="_automatic_fallback", on_change=save_preference, args=("automatic_fallback",))
    st.caption("Ollama failures never select OpenAI. Remote Ollama requires a secured endpoint configured on the server.")
    st.caption("OpenAI server credential: " + ("Configured" if settings.openai_api_key else "Missing"))
    if st.session_state.selected_provider == "openai":
        st.info("OpenAI sends questions and synthetic evidence to the cloud. Connection tests and analysis use your API account.")
    else: st.info("Ollama requires an installed model. Use a smaller model if the default does not fit your hardware.")
    if st.button("Test Connection", type="primary"):
        manager = None
        try:
            manager = manager_from_settings(settings, st.session_state.selected_provider, st.session_state.ollama_model, st.session_state.openai_model, st.session_state.automatic_fallback)
            status = manager.test_connection()
            st.session_state.connection_status = status
            st.session_state.last_fallback_reason = status.get("fallback_reason")
            if status.get("models"): st.session_state.ollama_models = status["models"]
            st.success("Inference connection verified.")
        except ProviderError as error:
            st.session_state.connection_status = {"provider":st.session_state.selected_provider,"inference_verified":False,
                "error_code":error.code,"fallback_reason":manager.last_fallback_reason}
            st.session_state.last_fallback_reason = manager.last_fallback_reason
            st.warning(str(error))
        except ValueError:
            st.session_state.connection_status = {"provider":st.session_state.selected_provider,"inference_verified":False,"error_code":"configuration"}
            st.warning("Provider configuration rejected. Verify server settings or select deterministic demo mode.")
        finally:
            if manager is not None: manager.close()
    st.write("Connection status")
    st.json(st.session_state.get("connection_status", {"inference_verified":False,"status":"Not tested"}))
    last = st.session_state.get("last_answer")
    connection = st.session_state.get("connection_status", {})
    st.caption("Active provider selection: " + st.session_state.selected_provider)
    st.caption("Last provider used: " + (last.provider if last else connection.get("provider","Not tested")))
    st.caption("Last fallback reason: " + (st.session_state.get("last_fallback_reason",last.fallback_reason if last else connection.get("fallback_reason")) or "None"))


def switch_suggested_domain():
    st.session_state.context=PlatformContext(domain=st.session_state.suggested_domain)
    st.session_state.pop("last_answer",None)


def workspace(settings, engine, scope=AccessScope()):
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.subheader("Analytics assistant")
        for message in st.session_state.messages[-12:]:
            with st.chat_message(message["role"]): st.write(message["content"])
        question = st.chat_input("Ask about fictional account usage or sales", key="question")
        available=list(scope.domains)
        st.selectbox("Suggested domain",available,format_func=lambda name:domain_registry()[name].name,
            key="suggested_domain",on_change=switch_suggested_domain)
        with st.expander("Suggested questions", expanded=not st.session_state.messages):
            for index, demo in enumerate(SALES_DEMOS if st.session_state.suggested_domain=="sales" else DEMOS):
                if st.button(demo, key=f"demo_{index}", width="stretch"): question = demo
        previous = st.session_state.get("last_answer")
        if previous and previous.status == "ok":
            with st.expander("Follow-up investigations"):
                for index, followup in enumerate(previous.followups):
                    if st.button(followup, key=f"followup_{index}", width="stretch"): question = followup
        if question:
            mode = "demo" if settings.public_demo_enabled or st.session_state.demo_mode else st.session_state.selected_provider
            manager = None
            try:
                manager = None if mode == "demo" else manager_from_settings(settings, mode, st.session_state.ollama_model, st.session_state.openai_model, st.session_state.automatic_fallback)
                with st.status("Understanding → Skill Selection → Query Execution → Validation → Findings", expanded=True) as status:
                    answer = PlatformAgent(SkillRegistry(engine),lambda:SalesSkills(sales_engine(settings.result_limit)),settings,scope).run(question, st.session_state.context, mode, manager)
                    for step in answer.trace: st.write(f"{step['stage']} · {step.get('skill','')} · {step['status']}")
                    status.update(label="Analysis complete" if answer.status == "ok" else "Analysis needs attention", state="complete" if answer.status == "ok" else "error", expanded=False)
                st.session_state.last_answer, st.session_state.context = answer, answer.context
                st.session_state.last_fallback_reason = answer.fallback_reason
                st.session_state.messages.extend([{"role":"user","content":question},{"role":"assistant","content":answer.message}])
                st.session_state.messages = st.session_state.messages[-12:]
                st.rerun()
            except ValueError: st.warning("Provider configuration is invalid. Review Settings or enable deterministic demo mode.")
            finally:
                if manager is not None: manager.close()
    with right:
        st.subheader("Analytical results")
        answer = st.session_state.get("last_answer")
        if answer: results_panel(answer)
        else:
            st.info("Ask a question to calculate results from the synthetic warehouse.")
            st.caption("No LLM is required when you explicitly enable deterministic demo mode.")


def main():
    try: settings = load_settings()
    except (ValueError,OverflowError):
        st.error("Server configuration is invalid. Check provider selection and finite, positive execution limits.")
        st.stop()
    st.set_page_config(page_title=settings.app_title, page_icon="📊", layout="wide")
    st.markdown("<style>h1{font-size:1.9rem!important}h2{font-size:1.3rem!important}h3{font-size:1.05rem!important}.block-container{padding-top:1.7rem}.stMetric{border:1px solid #e6ebef;border-radius:8px;padding:12px}</style>", unsafe_allow_html=True)
    st.caption("BDC / ANALYTICS WORKSPACE")
    st.title(settings.app_title)
    st.caption("Synthetic data only · Usage: July–September 2026 · Sales: April–September 2026 · UTC")
    scope = current_scope(settings)
    defaults = {"selected_provider":settings.llm_provider,"ollama_model":settings.ollama_model,
        "openai_model":settings.openai_model,"automatic_fallback":settings.fallback_to_ollama,
        "demo_mode":False,"messages":[],"context":PlatformContext()}
    for key, value in defaults.items():
        if key not in st.session_state: st.session_state[key] = value
    if settings.public_demo_enabled:
        st.session_state.demo_mode = True
        st.info("Public synthetic demo · No sign-in required · Deterministic analytics · No LLM calls")
    with st.sidebar:
        pages = ["Analytics Workspace","Agent Execution","Settings","Data Explorer","Evaluation Dashboard"]
        if settings.public_demo_enabled:
            pages.remove("Settings")
            if st.session_state.get("page") not in pages: st.session_state.page = pages[0]
        page = st.selectbox("Workspace section", pages, key="page")
        st.toggle("Deterministic demo mode", key="demo_mode", disabled=settings.public_demo_enabled)
        st.caption("Mode: " + ("Deterministic demo · no LLM" if st.session_state.demo_mode else st.session_state.selected_provider))
        if not st.session_state.demo_mode:
            st.caption("A configured LLM connection is required. Use Settings to test it.")
            if not st.session_state.get("connection_status",{}).get("inference_verified") and not st.session_state.get("last_answer"):
                st.warning("LLM connection unverified. Test it in Settings or explicitly enable deterministic demo mode.")
        if st.button("Clear conversation"):
            st.session_state.context, st.session_state.messages = PlatformContext(), []
            st.session_state.pop("last_answer", None)
            st.rerun()
    engine = analytical_engine(settings.result_limit)
    if not (engine.data_dir / "manifest.json").is_file():
        st.warning("Synthetic datasets are missing. Follow the generation instructions in README before analysis.")
        return
    if settings.public_demo_enabled:
        try:
            manifest = json.loads((engine.data_dir / "manifest.json").read_text(encoding="utf-8"))
            if engine.data_dir != (PROJECT_ROOT / "data" / "synthetic").resolve() or manifest.get("is_synthetic") is not True:
                raise ValueError("Public data must be the bundled synthetic warehouse.")
        except (ValueError, OSError, AttributeError):
            st.error("Public demo data validation failed. Only the bundled synthetic warehouse is permitted.")
            st.stop()
    if page == "Analytics Workspace": workspace(settings, engine,scope)
    elif page == "Settings": settings_panel(settings)
    elif page == "Agent Execution":
        st.subheader("Agent Execution")
        answer = st.session_state.get("last_answer")
        if answer: trace_panel(answer)
        else: st.info("Run an analysis to see completed skills and validation steps.")
    elif page == "Data Explorer":
        st.subheader("Data Explorer · Synthetic data")
        source=st.selectbox("Data domain",list(scope.domains),key="explorer_domain")
        selected_engine=sales_engine(settings.result_limit) if source=="sales" else engine
        if source=="sales" and settings.public_demo_enabled:
            try:
                marker=json.loads((selected_engine.data_dir/"manifest.json").read_text(encoding="utf-8"))
                if selected_engine.data_dir!=(PROJECT_ROOT/"data"/"synthetic_sales").resolve() or marker.get("is_synthetic") is not True: raise ValueError()
            except (OSError,ValueError):
                st.error("Public sales data validation failed.")
                return
        table = st.selectbox("Dataset", list(SALES_TABLES if source=="sales" else TABLES))
        try: schema, count, sample = selected_engine.explore(table,scope)
        except (PermissionError,TimeoutError,FileNotFoundError):
            st.warning("Data Explorer is unavailable for this account or warehouse state. Use scoped analytics or retry later.")
            return
        st.metric("Dataset rows", f"{count:,}")
        st.dataframe(pd.DataFrame(schema, columns=["column","type","nullable","key","default","extra"]), hide_index=True)
        st.dataframe(sample, hide_index=True, width="stretch")
        st.caption("Read-only samples. All account, user and device identifiers are fictional.")
    else:
        st.subheader("Evaluation Dashboard")
        report_path = PROJECT_ROOT / "reports" / "evaluation.json"
        if report_path.is_file(): st.json(json.loads(report_path.read_text(encoding="utf-8")))
        else: st.info("The evaluation report has not been generated yet.")
        st.write("Supported skills: " + ", ".join(list(SkillRegistry.names.values())+list(SalesSkills.names.values())))
        st.json({key:value.model_dump() for key,value in domain_registry().items()})
        st.caption("Synthetic evaluation does not establish enterprise production accuracy. Live provider tests are tracked separately.")
