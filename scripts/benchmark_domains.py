"""Actual four-domain Streamlit execution and export memory check; no providers."""
import json
import os
from datetime import datetime,timezone
from streamlit.testing.v1 import AppTest
from analytics_agent.config import PROJECT_ROOT
from scripts.benchmark import peak_memory_mb


def benchmark():
    os.environ.update(APP_ENV='production',PUBLIC_DEMO_ENABLED='true',OPENAI_API_KEY='',DUCKDB_MEMORY_LIMIT='320MB',RESULT_LIMIT='100',INVESTIGATION_TIMEOUT_SECONDS='180')
    app=AppTest.from_file(str(PROJECT_ROOT/'app.py'),default_timeout=180).run();results=[]
    for domain in ('usage','sales','marketing','finance'):
        app.selectbox(key='suggested_domain').select(domain).run();app.button(key='demo_0').click().run()
        if app.exception:raise AssertionError('Four-domain Streamlit exception')
        answer=app.session_state['last_answer']
        if answer.status!='ok' or not all(t['status']=='complete' for t in answer.trace):raise AssertionError(answer.message)
        results.append({'domain':domain,'status':answer.status,'elapsed_ms':round(answer.elapsed_ms,3),'baseline':answer.results[0].baseline,'current':answer.results[0].current,'executed_component_count':len(answer.trace),'export_buttons':len(app.get('download_button'))})
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'status':'pass','duckdb_memory_limit':'320MB','result_limit':100,'results':results,'peak_process_memory_mib':peak_memory_mb(),
        'limitation':'Single-process Windows Streamlit AppTest, with generated downloads. Not hosted memory telemetry or sustained load certification.'}
    (PROJECT_ROOT/'reports'/'four_domain_memory_smoke.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':print(json.dumps(benchmark(),indent=2))
