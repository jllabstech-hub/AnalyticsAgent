"""Execute every documented domain demo and record actual component evidence."""
import json
import os
from datetime import datetime,timezone
from dataclasses import replace
from analytics_agent.config import PROJECT_ROOT,load_settings
from analytics_agent.models import AccessScope,ALL_DOMAINS
from analytics_agent.platform import PlatformAgent
from analytics_agent.engine import Engine
from analytics_agent.skills import SkillRegistry
from analytics_agent.sales_engine import SalesEngine
from analytics_agent.sales_skills import SalesSkills
from analytics_agent.business_engine import BusinessEngine
from analytics_agent.business_skills import BusinessSkills
from analytics_agent.agent import DEMOS
from analytics_agent.sales_parser import SALES_DEMOS
from analytics_agent.business_parser import BUSINESS_DEMOS


def trace():
    settings=replace(load_settings(),public_demo_enabled=True)
    options={'memory':os.getenv('DUCKDB_MEMORY_LIMIT','320MB'),'result_limit':settings.result_limit}
    runner=PlatformAgent(SkillRegistry(Engine(**options)),SalesSkills(SalesEngine(**options)),scope=AccessScope(domains=ALL_DOMAINS),settings=settings,
        business_skills={domain:BusinessSkills(domain,BusinessEngine(domain,**options)) for domain in BUSINESS_DEMOS})
    demonstrations=[]
    for domain,questions in {'usage':DEMOS,'sales':SALES_DEMOS,**BUSINESS_DEMOS}.items():
        context=None
        for question in questions:
            answer=runner.run(question,context,mode='demo')
            if answer.status!='ok' or len(answer.trace)!=7 or any(t['status']!='complete' for t in answer.trace):
                raise AssertionError(f'{domain} demo failed: {answer.message}')
            context=answer.context
            demonstrations.append({'domain':domain,'question':question,'answer':answer.model_dump(mode='json')})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'status':'pass','domains':list(ALL_DOMAINS),'executed_demos':len(demonstrations),'mode':'deterministic; no LLM calls','demonstrations':demonstrations,
        'limitations':['Fictional bundled data only.','Live Marketing/Finance provider inference and real identity lifecycle are unverified.','Finance is an analytical subtotal, not a double-entry ledger or audited net income.','Cross-domain joins and real enterprise connectors are not registered.']}
    path=PROJECT_ROOT/'reports'/'four_domain_pipeline_trace.json';path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return {'status':report['status'],'domains':report['domains'],'executed_demos':len(demonstrations),'component_events':len(demonstrations)*7}


if __name__=='__main__':print(json.dumps(trace(),indent=2))
