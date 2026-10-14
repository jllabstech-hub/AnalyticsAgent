"""Documented whole-month domain grammar; unknown words/filters are refused."""
import re
from analytics_agent.business_models import BusinessContext, BusinessPlan, BusinessRequest, ENTITIES, CHANNELS, CATEGORIES
from analytics_agent.sales_parser import MONTHS

BUSINESS_DEMOS={
    'marketing':[
        'Compare marketing click through rate in Q3 versus Q2 2026.',
        'Which campaigns contributed to the change in marketing conversions in Q3 versus Q2 2026?',
        'Investigate marketing spend across channels in Q3 compared with Q2 2026.',
        'Compare marketing conversions in August and September 2026 for all markets.',
        'Now compare only Campaign Aurora for the same periods.'],
    'finance':[
        'Compare finance profit in Q3 versus Q2 2026.',
        'Which departments contributed to the change in finance expenses in Q3 versus Q2 2026?',
        'Investigate finance profit across categories in Q3 compared with Q2 2026.',
        'Compare finance profit margin in August and September 2026 for all markets.',
        'Now compare only Department Boreal for the same periods.']}
METRIC_PHRASES={
    'marketing':{'click_through_rate':('click through rate','click-through rate','ctr'),'conversion_rate':('conversion rate',),
        'cost_per_click':('cost per click','cpc'),'marketing_spend':('marketing spend','campaign spend','spend'),
        'conversions':('conversions',),'impressions':('impressions',),'clicks':('clicks',)},
    'finance':{'profit_margin':('profit margin','margin'),'finance_revenue':('finance revenue','booked revenue','revenue'),
        'expenses':('expenses','expense'),'profit':('profit',)}}


def parse_business(question,domain,context=BusinessContext()):
    text=question.strip().lower()
    def stop(message,action='clarify'):return BusinessPlan(action=action,message=message)
    if len(text)>2000 or re.search(r'\b(sql|delete|drop|password|employee|forecast|predict|cash|tax|balance|confirmed cause)\b',text):return stop('Use only the registered synthetic domain metrics and comparisons.','unsupported')
    if re.search(r'\b(202[0-57-9]|20[013-9]\d|january|february|march|october|november|december|q[14])\b',text):return stop('This domain covers April–September 2026 only.','unsupported')
    if re.search(r'\b(?:april|may|june|july|august|september)\s+\d{1,2}\b|\d{4}-\d{2}-\d{2}',text):return stop('Use two whole months or Q3 versus Q2 2026.')
    if not re.search(r'\b(show|compare|which|investigate|why|now)\b',text):return stop('Ask for a metric comparison or contribution with two periods.')
    previous=context.request if context.request and context.request.domain==domain else None
    metric_text=re.split(r'\b(?:for|only)\b|\bin\s+(?:market|campaign|department|channel|category)\b',text,maxsplit=1)[0]
    metric=None
    for name,phrases in METRIC_PHRASES[domain].items():
        if any(re.search(r'\b'+re.escape(phrase)+r'\b',metric_text) for phrase in phrases):
            if metric is not None:return stop('Compare one metric per question.')
            metric=name
            for phrase in phrases:metric_text=re.sub(r'\b'+re.escape(phrase)+r'\b',' ',metric_text)
    if metric is None and previous and re.search(r'same periods|now|contributed',text):metric=previous.metric
    if metric is None:return stop('Choose a registered '+domain+' metric.')
    data=previous.model_dump(mode='json') if previous else BusinessRequest(domain=domain,metric=metric).model_dump(mode='json')
    data['metric']=metric
    quarters=re.findall(r'\bq([23])\b',text);months=re.findall(r'\b(april|may|june|july|august|september)\b',text)
    relative=bool(re.search(r'last (?:three|3) months|last complete quarter',text))
    if relative or set(quarters)=={'2','3'}:
        data['baseline']={'start':'2026-04-01','end':'2026-07-01'};data['current']={'start':'2026-07-01','end':'2026-10-01'}
    elif months:
        chosen=list(dict.fromkeys(MONTHS[m] for m in months))
        if len(chosen)!=2:return stop('Specify exactly two whole months.')
        for period,month in zip(('baseline','current'),chosen):data[period]={'start':f'2026-{month:02}-01','end':f'2026-{month+1:02}-01'}
    elif not previous:return stop('Specify Q3 versus Q2 2026, or two months in April–September.')
    if quarters and not relative and set(quarters)!={'2','3'}:return stop('Specify both Q2 and Q3 2026.')
    markets=re.findall(r'\bmarket\s+([a-z][\w-]*)\b',text)
    if len(set(markets))>1:return stop('Use one market filter or request a market breakdown.')
    if markets:
        if markets[0] not in 'abcde' or len(markets[0])!=1:return stop('Use fictional Market A–E.','unsupported')
        data['market']='Market '+markets[0].upper()
    found=[name for name in ENTITIES[domain] if name.lower() in text]
    channels=[name for name in CHANNELS if name.lower() in text]
    categories=[name for name in CATEGORIES if re.search(r'\b'+re.escape(name.lower())+r'\b',text)] if domain=='finance' else []
    # "finance revenue" names a metric, not an implicit Revenue-only filter.
    categories=[name for name in categories if name!='Revenue' or re.search(r'(?:category|only)\s+revenue\b',text)]
    for names,key in ((found,'entity'),(channels,'channel'),(categories,'category')):
        if len(names)>1:return stop('Choose one filter or request its breakdown.')
        if names:data[key]=names[0]
    residual=text
    for name in (*ENTITIES[domain],*CHANNELS,*CATEGORIES):residual=residual.replace(name.lower(),' ')
    residual=re.sub(r'\bmarket\s+[a-e]\b|\bq[23]\b|\b2026\b',' ',residual)
    allowed=set('show compare which investigate why now only for in on with versus vs and the same periods period to of across all markets market campaigns campaign departments department channels channel categories category finance marketing booked revenue expense expenses profit margin conversions conversion impressions clicks click through click-through rate ctr cpc cost per spend contributed contribute contribution change changes growth decline declined decrease decreased increase increased performance compared previous quarter last complete three months 3 baseline current breakdown primary incomplete scenario data calendar fiscal'.split())|set(MONTHS)
    if any(w not in allowed for w in re.findall(r'[a-z0-9_-]+',residual)):return stop('Unregistered entity, filter or operation. Use the fictional domain catalog.','unsupported')
    for phrase,key in (('all markets','market'),('all campaigns','entity'),('all departments','entity'),('all channels','channel'),('all categories','category')):
        if phrase in text:data[key]=None
    if 'incomplete' in text:data['scenario']='incomplete'
    if 'primary' in text:data['scenario']='primary'
    operation='investigation' if 'investigate' in text or 'why' in text else 'contribution' if 'contribut' in text or 'which' in text else 'comparison'
    dimension='campaign' if 'campaigns' in text else 'department' if 'departments' in text else 'channel' if 'channels' in text else 'category' if 'categories' in text else 'market'
    if operation in ('contribution','investigation'):
        key={'campaign':'entity','department':'entity','channel':'channel','category':'category','market':'market'}[dimension]
        explicit={'entity':found,'channel':channels,'category':categories,'market':markets}[key]
        if not explicit:data[key]=None
    try:return BusinessPlan(action='execute',request=BusinessRequest.model_validate(data),operation=operation,dimension=dimension)
    except ValueError:return stop('The requested filter or dimension is not supported by this domain.','unsupported')
