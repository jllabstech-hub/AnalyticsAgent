"""Regression for a local launch following a locked demo launch."""
from unittest.mock import Mock
import pytest
from scripts import run_local


@pytest.mark.parametrize('demo,expected', [(False,'false'), (True,'true')])
def test_local_start_mode_overrides_inherited_demo_flag(monkeypatch,demo,expected):
    monkeypatch.setenv('PUBLIC_DEMO_ENABLED','true')
    monkeypatch.setenv('LLM_PROVIDER','ollama')
    monkeypatch.setattr('sys.argv',['run_local','--port','8514']+(['--demo'] if demo else []))
    application=Mock()
    monkeypatch.setattr(run_local.st,'App',Mock(return_value=application))
    server=Mock()
    monkeypatch.setattr(run_local.uvicorn,'run',server)
    run_local.main()
    import os
    assert os.environ['PUBLIC_DEMO_ENABLED']==expected
    assert os.environ['LLM_PROVIDER']=='ollama'
    assert server.call_args.kwargs['host']=='localhost'
    assert server.call_args.kwargs['port']==8514
