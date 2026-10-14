"""Two fixed domain adapters sharing guarded query/quality mechanics."""
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import time
import duckdb
import yaml
from typing import Literal
from analytics_agent.config import PROJECT_ROOT
from analytics_agent.engine import Engine, DEADLINE
from analytics_agent.models import Contract, AccessScope
from analytics_agent.business_models import BusinessRequest, BusinessDomain, DIMENSIONS, ENTITIES, METRICS

COUNTERS={"marketing":("impressions","clicks","conversions","spend_cents"),"finance":("revenue_cents","expense_cents","profit_cents")}


class BusinessDefinition(Contract):
    metric_id: str
    domain: BusinessDomain
    version: str
    owner: str
    timezone: Literal["UTC"]
    currency: Literal["USD"]
    unit: Literal["usd","count","ratio"]
    additive: bool
    supported_dimensions: list[str]
    source_datasets: list[str]
    required_joins: list[str]
    data_quality_requirements: list[str]
    business_meaning: str
    calculation_method: str
    aggregation_grain: str
    numerator: str
    denominator: str | None


@lru_cache(maxsize=2)
def business_definitions(domain):
    raw=yaml.safe_load(Path(__file__).with_name("business_metrics.yaml").read_text(encoding="utf-8"))[domain]
    common={key:raw[key] for key in ("owner","supported_dimensions","source_datasets","required_joins")}
    definitions={key:BusinessDefinition.model_validate({**common,**value,"domain":domain}) for key,value in raw["metrics"].items()}
    if set(definitions)!=set(METRICS[domain]) or any(key!=d.metric_id for key,d in definitions.items()): raise ValueError("Domain semantic registry mismatch")
    return definitions


class BoundBusinessQuery(Contract):
    request: BusinessRequest
    kind: Literal["total","trend","breakdown"]
    period: Literal["baseline","current"]
    dimension: str
    template: str
    sql: str
    parameters: tuple[str,...]


def business_value(row,metric):
    if metric in ("impressions","clicks","conversions"): return row[metric]
    amounts={"marketing_spend":"spend_cents","finance_revenue":"revenue_cents","expenses":"expense_cents","profit":"profit_cents"}
    if metric in amounts: return row[amounts[metric]]/100
    ratios={"click_through_rate":("clicks","impressions",1),"conversion_rate":("conversions","clicks",1),
            "cost_per_click":("spend_cents","clicks",100),"profit_margin":("profit_cents","revenue_cents",1)}
    numerator,denominator,scale=ratios[metric]
    return row[numerator]/scale/row[denominator] if row[denominator] else None


class BusinessEngine(Engine):
    def __init__(self,domain,data_dir=None,**kwargs):
        if domain not in METRICS: raise ValueError("Unregistered analytical domain")
        self.domain=domain
        self.fact=f"{domain}_fact"
        self.entity_table="campaign_dim" if domain=="marketing" else "department_dim"
        self.tables=(self.fact,self.entity_table,"market_dim","calendar_dim","data_quality_status")
        self.dimensions={"market":"market","campaign":"entity_name","department":"entity_name","channel":"channel","category":"category"}
        super().__init__(data_dir or PROJECT_ROOT/"data"/f"synthetic_{domain}",**kwargs)

    def authorize(self,request,scope):
        if request.domain!=self.domain or self.domain not in scope.domains or not scope.markets: raise PermissionError("Domain outside authorized scope.")
        if request.market and request.market not in scope.markets: raise PermissionError("Market outside authorized scope.")

    @contextmanager
    def session(self,scenario="primary"):
        if scenario not in ("primary","incomplete"): raise ValueError("Unknown scenario")
        remaining=min(self.timeout,DEADLINE.get()-time.perf_counter()) if DEADLINE.get() is not None else self.timeout
        if remaining<=0 or not self._session_slot.acquire(timeout=remaining): raise TimeoutError("Analytics is busy or its deadline expired.")
        connection=None
        try:
            connection=duckdb.connect(config={"threads":1,"memory_limit":self.memory,"temp_directory":"","preserve_insertion_order":False,"autoinstall_known_extensions":False,"autoload_known_extensions":False})
            files=[]
            for table in self.tables:
                file=self.data_dir/("incomplete" if table==self.fact and scenario=="incomplete" else "")/f"{table}.parquet"
                if not file.is_file(): raise FileNotFoundError("Synthetic domain dataset missing. Run scripts.generate_business_data.")
                path=str(file).replace("\\","/");files.append(path)
                connection.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{path.replace(chr(39),chr(39)*2)}')")
            connection.execute(f"CREATE VIEW canonical_events AS SELECT * EXCLUDE(rank) FROM (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY ingested_at) rank FROM {self.fact}) WHERE rank=1")
            derived=", f.revenue_cents-f.expense_cents profit_cents" if self.domain=="finance" else ""
            connection.execute(f"""CREATE VIEW joined_events AS SELECT f.*,e.entity_name,m.market,c.month_label{derived}
                FROM canonical_events f JOIN {self.entity_table} e USING(entity_id) JOIN market_dim m USING(market_id)
                JOIN calendar_dim c USING(activity_date) WHERE f.activity_at>=e.valid_from AND f.activity_at<e.valid_to""")
            connection.execute("SET allowed_paths=?",[files]);connection.execute("SET enable_external_access=false");connection.execute("SET lock_configuration=true")
            yield connection
        finally:
            if connection is not None: connection.close()
            self._session_slot.release()

    def filters(self,request,scope):
        self.authorize(request,scope)
        clauses=["market IN ("+",".join("?" for _ in scope.markets)+")"];params=list(scope.markets)
        for field,column in (("market","market"),("entity","entity_name"),("channel","channel"),("category","category")):
            value=getattr(request,field)
            if value is not None: clauses.append(f"{column}=?");params.append(value)
        return " AND ".join(clauses),params

    def prepare(self,request,scope,kind="total",period="baseline",dimension="market"):
        request=BusinessRequest.model_validate(request.model_dump() if isinstance(request,BusinessRequest) else request)
        if kind not in ("total","trend","breakdown") or period not in ("baseline","current") or dimension not in DIMENSIONS[self.domain]: raise ValueError("Unapproved domain query")
        where,params=self.filters(request,scope);bounds=getattr(request,period)
        counters=COUNTERS[self.domain]; amounts=", ".join(f"SUM({field})::BIGINT {field}" for field in counters)
        group={"total":"'All'","trend":"month_label","breakdown":self.dimensions[dimension]}[kind]
        sql=f"SELECT {group} group_name,{amounts} FROM joined_events WHERE activity_date>=?::DATE AND activity_date<?::DATE AND {where}"
        if kind!="total": sql+=f" GROUP BY {group} ORDER BY {group}"
        bindings=[bounds.start.isoformat(),bounds.end.isoformat()]+params
        if kind=="trend":
            output=", ".join(f"COALESCE({field},0)::BIGINT {field}" for field in counters)
            sql=f"""WITH spine AS (SELECT DISTINCT month_label FROM calendar_dim WHERE activity_date>=?::DATE AND activity_date<?::DATE),
                amounts AS (SELECT month_label,{amounts} FROM joined_events WHERE activity_date>=?::DATE AND activity_date<?::DATE AND {where} GROUP BY month_label)
                SELECT spine.month_label group_name,{output} FROM spine LEFT JOIN amounts USING(month_label) ORDER BY spine.month_label"""
            bindings=[bounds.start.isoformat(),bounds.end.isoformat()]+bindings
        return BoundBusinessQuery(request=request,kind=kind,period=period,dimension=dimension,template=f"{self.domain}.{kind}.{request.metric}.{dimension}",sql=sql,parameters=tuple(bindings))

    def execute_bound(self,bound,scope):
        if bound!=self.prepare(bound.request,scope,bound.kind,bound.period,bound.dimension): raise PermissionError("Query binding was modified; execution denied.")
        with self.session(bound.request.scenario) as con:
            rows,evidence=self._execute(con,bound.sql,list(bound.parameters),bound.template,bound.request,
                {"executed_period":getattr(bound.request,bound.period).model_dump(mode="json"),"authorized_scope":scope.model_dump(mode="json"),"sql_sha256":hashlib.sha256(bound.sql.encode()).hexdigest()},source_names=list(self.tables[:4]))
        for row in rows:
            for field in COUNTERS[self.domain]: row[field]=row[field] or 0
            row["value"]=business_value(row,bound.request.metric)
        return rows,evidence

    def knowledge(self,request,scope):
        self.authorize(request,scope);schemas={};evidence=[]
        with self.session(request.scenario) as con:
            for table in self.tables:
                schemas[table],item=self._execute(con,f"DESCRIBE {table}",[],f"{self.domain}.schema.{table}",request,source_names=[table]);evidence.append(item)
        catalog=yaml.safe_load(Path(__file__).with_name("business_metrics.yaml").read_text(encoding="utf-8"))[self.domain]["catalog"]
        return {"metric":business_definitions(self.domain)[request.metric].model_dump(),"catalog":catalog,"schemas":schemas,
            "synthetic_manifest":json.loads((self.data_dir/"manifest.json").read_text(encoding="utf-8"))},evidence

    def quality(self,request,scope):
        where,params=self.filters(request,scope)
        fields=COUNTERS[self.domain] if self.domain=="marketing" else COUNTERS[self.domain][:2]
        signature="("+",".join(("entity_id","market_id","activity_date","activity_at","currency",*(fields),"channel" if self.domain=="marketing" else "category"))+")"
        nulls=" OR ".join(f"{field} IS NULL" for field in ("event_id","entity_id","market_id","activity_date","activity_at","ingested_at","currency",*fields))
        valid_values="impressions<>1 OR clicks NOT IN (0,1) OR conversions<0 OR conversions>clicks OR spend_cents<0 OR channel IS NULL OR channel NOT IN ('Channel Search','Channel Social','Channel Email')" if self.domain=="marketing" else "revenue_cents<0 OR expense_cents<0 OR category IS NULL OR NOT ((category='Revenue' AND revenue_cents>0 AND expense_cents=0) OR (category IN ('Cost of Goods','Operating Expense') AND revenue_cents=0 AND expense_cents>0))"
        quoted=",".join("'"+field+"'" for field in fields)
        checks=f"""SELECT
            (SELECT COUNT(*) FROM information_schema.columns WHERE table_name='{self.fact}' AND column_name IN ({quoted}) AND data_type NOT IN ('BIGINT','INTEGER','SMALLINT','TINYINT','HUGEINT','UBIGINT','UINTEGER','USMALLINT','UTINYINT')) invalid_schema,
            (SELECT COUNT(*) FROM (SELECT entity_id FROM {self.entity_table} GROUP BY entity_id HAVING COUNT(*)<>1))+
            (SELECT COUNT(*) FROM (SELECT market_id FROM market_dim GROUP BY market_id HAVING COUNT(*)<>1))+
            (SELECT COUNT(*) FROM (SELECT activity_date FROM calendar_dim GROUP BY activity_date HAVING COUNT(*)<>1)) invalid_keys,
            (SELECT COUNT(*) FROM canonical_events f LEFT JOIN {self.entity_table} e USING(entity_id) LEFT JOIN market_dim m USING(market_id) LEFT JOIN calendar_dim c USING(activity_date)
                WHERE e.entity_id IS NULL OR m.market_id IS NULL OR c.activity_date IS NULL OR e.valid_from IS NULL OR e.valid_to IS NULL OR e.valid_from>=e.valid_to OR f.activity_at<e.valid_from OR f.activity_at>=e.valid_to) invalid_joins,
            (SELECT COUNT(*) FROM (SELECT event_id FROM {self.fact} GROUP BY event_id HAVING COUNT(DISTINCT {signature})>1)) conflicting_duplicates,
            (SELECT COUNT(*) FROM canonical_events WHERE {nulls} OR {valid_values} OR currency<>'USD' OR DATE_TRUNC('day',activity_at)<>activity_date OR ingested_at<activity_at) invalid_values,
            (SELECT COUNT(*) FROM {self.entity_table} WHERE entity_name IS NULL OR entity_name NOT IN ({','.join(repr(n) for n in ENTITIES[self.domain])})) invalid_entities,
            (SELECT COUNT(*) FROM market_dim WHERE market IS NULL OR market NOT IN ('Market A','Market B','Market C','Market D','Market E')) invalid_markets,
            (SELECT COUNT(*) FROM (SELECT scenario,dataset,period_start FROM data_quality_status GROUP BY ALL HAVING COUNT(*)<>1)) invalid_quality_grain"""
        evidence=[]
        with self.session(request.scenario) as con:
            rows,item=self._execute(con,checks,[],f"{self.domain}.quality.integrity",request,source_names=list(self.tables));evidence.append(item)
            if any(rows[0].values()): raise ValueError("Domain source schema, grain, values or temporal joins failed; results withheld.")
            start=min(request.baseline.start,request.current.start);end=max(request.baseline.end,request.current.end)
            stats_sql=f"""WITH scoped AS (SELECT f.*,e.entity_name,m.market FROM {self.fact} f JOIN {self.entity_table} e USING(entity_id) JOIN market_dim m USING(market_id)
                WHERE activity_date>=?::DATE AND activity_date<?::DATE AND {where}), arrivals AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_id ORDER BY ingested_at) arrival_rank FROM scoped)
                SELECT COUNT(*) raw_rows,COUNT(DISTINCT event_id) unique_lines,COUNT(DISTINCT CASE WHEN arrival_rank=1 AND ingested_at>activity_at+INTERVAL '24 hours' THEN event_id END) late_lines FROM arrivals"""
            stats,item=self._execute(con,stats_sql,[start,end]+params,f"{self.domain}.quality.events",request,source_names=list(self.tables[:3]));evidence.append(item)
            coverage,item=self._execute(con,"SELECT * FROM data_quality_status WHERE scenario=? AND period_start<? AND period_end>?",[request.scenario,end,start],f"{self.domain}.quality.coverage",request,source_names=["data_quality_status"]);evidence.append(item)
        complete=True
        for table in self.tables:
            for period in (request.baseline,request.current):
                cursor=period.start
                for row in sorted((r for r in coverage if r['dataset']==table),key=lambda r:r['period_start']):
                    a=row['period_start'].date();b=min(row['period_end'],row['available_through']).date()
                    if row['complete'] and a<=cursor<b:cursor=b
                if cursor<period.end:complete=False
        fresh=bool(coverage) and all(r['loaded_at']<=r['snapshot_as_of'] and (r['snapshot_as_of']-r['loaded_at']).days<=2 for r in coverage)
        warnings=[]
        if not complete:warnings.append("Incomplete coverage: provisional results; partial months are labeled.")
        if not fresh:warnings.append("Historical snapshot freshness validation failed.")
        removed=stats[0]['raw_rows']-stats[0]['unique_lines']
        if removed:warnings.append(f"Removed {removed:,} duplicated observations.")
        if stats[0]['late_lines']:warnings.append(f"Included {stats[0]['late_lines']:,} observations arriving more than 24 hours late.")
        return {"complete":complete,"freshness_valid":fresh,"freshness_basis":"Historical synthetic snapshot 2026-10-10","integrity":"passed","coverage":coverage,"events":stats[0]},warnings,evidence

    def explore(self,table,scope):
        if table not in self.tables:raise ValueError("Unapproved domain table")
        self.authorize(BusinessRequest(domain=self.domain,metric=METRICS[self.domain][0]),scope)
        if set(scope.markets)!=set(AccessScope().markets):raise PermissionError("Explorer requires all-market authorization.")
        with self.session() as con:
            return con.execute(f"DESCRIBE {table}").fetchall(),con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],con.execute(f"SELECT * FROM {table} LIMIT ?",[min(20,self.result_limit)]).fetchdf()
