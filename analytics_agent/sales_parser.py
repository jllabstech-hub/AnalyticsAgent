"""Bounded, documented sales question grammar; unknown filters never disappear."""
import re
from analytics_agent.sales_models import SalesPlan, SalesRequest, SalesContext

SALES_DEMOS = ["Show Orion One sales performance in Market A for Q3 2026 compared with Q2 2026.",
    "Which markets contributed to the change in net sales in Q3 versus Q2 2026?",
    "Investigate net sales across products in Q3 compared with Q2 2026.",
    "Compare units sold in August and September 2026 for all markets.",
    "Now compare only Fictional Web for the same periods."]
PRODUCTS=("Orion One","Orion Plus","Nova Mini","Nova Fold")
CHANNELS=("Fictional Web","Fictional Shops","Fictional Partners")
MONTHS={"april":4,"may":5,"june":6,"july":7,"august":8,"september":9}


def parse_sales(question, context=SalesContext()):
    text=question.strip().lower()
    if len(text)>2000 or re.search(r"\b(sql|delete|drop|password|real data|employee|forecast|predict|confirmed cause)\b",text):
        return SalesPlan(action="unsupported",message="Only governed fictional sales questions are supported.")
    if re.search(r"\b(202[0-57-9]|20[013-9]\d|january|february|march|october|november|december|q[14])\b",text):
        return SalesPlan(action="unsupported",message="Sales data covers April–September 2026 (Q2 and Q3) only.")
    if not re.search(r"\b(show|compare|which|investigate|why|now)\b",text):
        return SalesPlan(action="clarify",message="Ask for a sales comparison or contribution, with two months or Q2/Q3 2026.")
    if re.search(r"\b(?:april|may|june|july|august|september)\s+\d{1,2}\b|\d{4}-\d{2}-\d{2}",text):
        return SalesPlan(action="clarify",message="Use whole-month names or Q2/Q3 2026 in the synthetic sales demo.")
    previous=context.request
    metric="avg_order_value" if re.search(r"average order value|avg order value|\baov\b",text) else "units_sold" if "units sold" in text else "orders" if re.search(r"\borders\b",text) else "net_sales" if re.search(r"\b(sales|revenue)\b",text) else None
    if metric is None:
        if previous and re.search(r"same periods|market|product|channel|fictional",text): metric=previous.metric
        else: return SalesPlan(action="clarify",message="Choose net sales, units sold, orders, or average order value.")
    data=previous.model_dump(mode="json") if previous else SalesRequest().model_dump(mode="json")
    data["metric"]=metric
    relative=bool(re.search(r"last (?:three|3) months|last complete quarter",text))
    quarters=re.findall(r"\bq([23])\b",text)
    months=re.findall(r"\b(april|may|june|july|august|september)\b",text)
    if relative or set(quarters)=={"2","3"}:
        data["baseline"]={"start":"2026-04-01","end":"2026-07-01"}
        data["current"]={"start":"2026-07-01","end":"2026-10-01"}
    elif months:
        chosen=list(dict.fromkeys(MONTHS[m] for m in months))
        if len(chosen)!=2: return SalesPlan(action="clarify",message="Specify two whole months for the comparison.")
        data["baseline"]={"start":f"2026-{chosen[0]:02}-01","end":f"2026-{chosen[0]+1:02}-01"}
        data["current"]={"start":f"2026-{chosen[1]:02}-01","end":f"2026-{chosen[1]+1:02}-01"}
    elif not previous: return SalesPlan(action="clarify",message="Which periods? Use Q3 versus Q2 2026, or two months within April–September.")
    if quarters and not relative and set(quarters)!={"2","3"}:
        return SalesPlan(action="clarify",message="Specify both Q2 and Q3 2026.")
    matches=re.findall(r"\bmarket\s+([a-z][\w-]*)\b",text)
    if len(set(matches))>1: return SalesPlan(action="clarify",message="Use one market filter or request a market contribution breakdown.")
    if matches:
        if matches[0] not in set("abcde"): return SalesPlan(action="unsupported",message="Use a fictional market: Market A–E.")
        data["market"]=f"Market {matches[0].upper()}"
    found=[name for name in PRODUCTS if name.lower() in text]
    if len(found)>1: return SalesPlan(action="clarify",message="Use one product filter or request a product breakdown.")
    if found: data["product"]=found[0]
    channels=[name for name in CHANNELS if name.lower() in text]
    if len(channels)>1: return SalesPlan(action="clarify",message="Use one channel filter or request a channel breakdown.")
    if channels: data["channel"]=channels[0]
    # This grammar must refuse real/unregistered countries and products rather than ignore them.
    residual=text
    for name in PRODUCTS+CHANNELS: residual=residual.replace(name.lower()," ")
    residual=re.sub(r"\bmarket\s+[a-e]\b|\bq[23]\b|\b2026\b", " ", residual)
    allowed=set("show compare which investigate why now only for in on with versus vs and the same periods period to of across all markets products channels market product channel sales net revenue performance contributed contribute contribution change growth average avg order value aov units sold orders compared previous quarter last complete three months 3 baseline current breakdown primary incomplete scenario data calendar fiscal".split()) | set(MONTHS)
    unknown=[word for word in re.findall(r"[a-z0-9_-]+",residual) if word not in allowed]
    if unknown: return SalesPlan(action="unsupported",message="An unregistered product, country, filter, or operation was requested. Use the fictional catalog and documented sales questions.")
    for phrase,key in (("all markets","market"),("all products","product"),("all channels","channel")):
        if phrase in text: data[key]=None
    if "incomplete" in text: data["scenario"]="incomplete"
    if "primary" in text: data["scenario"]="primary"
    operation="investigation" if "investigate" in text or "why" in text else "contribution" if "contribut" in text or "which" in text else "comparison"
    dimension="product" if "products" in text else "channel" if "channels" in text else "market"
    if operation in ("contribution","investigation"):
        if dimension=="market" and not matches: data["market"]=None
        if dimension=="product" and not found: data["product"]=None
        if dimension=="channel" and not channels: data["channel"]=None
    return SalesPlan(action="execute",request=SalesRequest.model_validate(data),operation=operation,dimension=dimension)
