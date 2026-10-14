import time
import pytest
import streamlit as st
from streamlit.runtime.secrets import AttrDict
from streamlit.testing.v1 import AppTest
from analytics_agent.access import scope_for_claims,valid_auth_configuration
from analytics_agent.config import PROJECT_ROOT,load_settings
from test_edge_cases import small

CLAIMS = {"iss":"https://idp.example","sub":"fictional-id","exp":2000}
ACCESS = {"https://idp.example|fictional-id":{"markets":["Market A"],"services":["Service Alpha"],"skills":["K1"]}}


def test_approved_identity_gets_only_its_server_scope():
    scope = scope_for_claims(CLAIMS,ACCESS,now=1000)
    assert scope.markets == ("Market A",) and scope.services == ("Service Alpha",) and scope.skills == ("K1",)


@pytest.mark.parametrize("change", [{"exp":1000},{"exp":float('nan')},{"exp":None},{"sub":"other"},{"iss":"https://untrusted.example"}])
def test_expired_missing_or_unapproved_claims_fail_closed(change):
    with pytest.raises(PermissionError): scope_for_claims({**CLAIMS,**change},ACCESS,now=1000)


@pytest.mark.parametrize("entry", [{},{"markets":[]},{"markets":["Market Z"],"services":["Service Alpha"],"skills":["K1"]}])
def test_malformed_scope_cannot_grant_default_full_access(entry):
    with pytest.raises(PermissionError): scope_for_claims(CLAIMS,{"https://idp.example|fictional-id":entry},now=1000)


def test_production_auth_configuration_requires_https_and_secrets():
    configuration = {"redirect_uri":"https://app.example/oauth2callback","server_metadata_url":"https://idp.example/.well-known/openid-configuration","client_id":"fictional-id","client_secret":"fictional-secret","cookie_secret":"fictional-cookie-secret-long-enough-for-test"}
    assert valid_auth_configuration(configuration)
    assert not valid_auth_configuration({**configuration,"redirect_uri":"http://app.example/oauth2callback"})
    assert not valid_auth_configuration({**configuration,"cookie_secret":"short"})
    assert not valid_auth_configuration({})


def test_hosted_mode_cannot_disable_auth_with_local_environment(monkeypatch):
    monkeypatch.setenv("RENDER","true")
    monkeypatch.setenv("APP_ENV","local")
    assert load_settings().app_env == "production"


def test_anonymous_production_session_has_no_analytics_or_provider_controls(monkeypatch):
    monkeypatch.setenv("APP_ENV","production")
    monkeypatch.setenv("OPENAI_API_KEY","fictional-server-key")
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    assert not app.exception and not app.chat_input and not app.metric and not app.radio
    assert any("Production access is disabled" in e.value for e in app.error)


def test_authenticated_ui_derives_scope_and_clears_results_after_revocation(small,monkeypatch):
    from analytics_agent import ui
    (small.data_dir / "manifest.json").write_text("{}",encoding="utf-8")
    class LoggedUser(dict): is_logged_in = True
    identity = LoggedUser({**CLAIMS,"exp":time.time()+600})
    scopes = {key:dict(value) for key,value in ACCESS.items()}
    configuration = {"redirect_uri":"https://app.example/oauth2callback","server_metadata_url":"https://idp.example/.well-known/openid-configuration","client_id":"fictional-id","client_secret":"fictional-secret","cookie_secret":"fictional-cookie-secret-long-enough-for-test"}
    monkeypatch.setenv("APP_ENV","production")
    monkeypatch.setattr(st,"user",identity)
    monkeypatch.setattr(st,"secrets",{"auth":AttrDict(configuration),"access":AttrDict(scopes)})
    monkeypatch.setattr(ui,"analytical_engine",lambda _:small)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"),default_timeout=30).run()
    app.toggle(key="demo_mode").set_value(True).run()
    app.chat_input[0].set_value("Compare August and September active users.").run()
    assert not app.exception and app.metric[0].value == "2" and app.metric[1].value == "1"
    app.chat_input[0].set_value("Now compare only Market B for the same periods.").run()
    assert app.session_state["last_answer"].status == "error" and not app.metric
    st.secrets["access"] = AttrDict({"https://idp.example|fictional-id":{"markets":["Market B"],"services":["Service Alpha"],"skills":["K1"]}})
    app.run()
    assert not app.exception and not app.metric and app.session_state["messages"] == []
