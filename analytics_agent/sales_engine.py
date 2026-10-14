"""Read-only sales adapter. Only regenerated approved query bindings execute."""
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import time
import duckdb
import yaml
from pydantic import BaseModel, ConfigDict
from analytics_agent.config import PROJECT_ROOT
from analytics_agent.engine import Engine, DEADLINE
from analytics_agent.models import AccessScope, Contract
from analytics_agent.sales_models import SalesRequest, SalesMetric, SalesDimension

SALES_TABLES = ("sales_fact", "product_dim", "market_dim", "calendar_dim", "data_quality_status")
DIMENSIONS = {"market":"market", "product":"product_name", "channel":"channel"}
AMOUNTS = "SUM(net_cents)::BIGINT net_cents, SUM(units_sold)::BIGINT units_sold, COUNT(DISTINCT order_id)::BIGINT orders"


class SalesDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric_id: SalesMetric
    version: str
    owner: str
    timezone: str
    currency: str
    supported_dimensions: list[SalesDimension]
    source_datasets: list[str]
    required_joins: list[str]
    data_quality_requirements: list[str]
    business_meaning: str
    calculation_method: str
    aggregation_grain: str
    numerator: str
    denominator: str | None


@lru_cache(maxsize=1)
def sales_definitions():
    raw = yaml.safe_load(Path(__file__).with_name("sales_metrics.yaml").read_text(encoding="utf-8"))
    definitions = {key:SalesDefinition.model_validate(value) for key,value in raw["metrics"].items()}
    if any(key != value.metric_id for key,value in definitions.items()): raise ValueError("Sales metric ID mismatch")
    return definitions


class BoundSalesQuery(Contract):
    request: SalesRequest
    kind: str
    period: str
    dimension: SalesDimension
    template: str
    sql: str
    parameters: tuple[str, ...]


def sales_value(row, metric):
    if metric == "net_sales": return row["net_cents"] / 100
    if metric == "units_sold": return row["units_sold"]
    if metric == "orders": return row["orders"]
    return row["net_cents"] / 100 / row["orders"] if row["orders"] else None


class SalesEngine(Engine):
    def __init__(self, data_dir=None, **kwargs):
        super().__init__(data_dir or PROJECT_ROOT / "data" / "synthetic_sales", **kwargs)

    def authorize(self, request, scope):
        if "sales" not in scope.domains or not scope.markets:
            raise PermissionError("Sales domain outside authorized scope.")
        if request.market and request.market not in scope.markets:
            raise PermissionError("Sales market outside authorized scope.")

    @contextmanager
    def session(self, scenario="primary"):
        if scenario not in ("primary", "incomplete"): raise ValueError("Unsupported sales scenario")
        remaining = min(self.timeout,DEADLINE.get()-time.perf_counter()) if DEADLINE.get() is not None else self.timeout
        if remaining <= 0 or not self._session_slot.acquire(timeout=remaining):
            raise TimeoutError("Analytics is busy or its deadline expired. Retry shortly.")
        connection = None
        try:
            connection = duckdb.connect(config={"threads":1,"memory_limit":self.memory,"temp_directory":"",
                "preserve_insertion_order":False,"autoinstall_known_extensions":False,"autoload_known_extensions":False})
            files = []
            for table in SALES_TABLES:
                file = self.data_dir / ("incomplete" if table == "sales_fact" and scenario == "incomplete" else "") / f"{table}.parquet"
                if not file.is_file(): raise FileNotFoundError("Bundled synthetic sales data missing. Run scripts.generate_sales_data.")
                path = str(file).replace("\\","/")
                files.append(path)
                connection.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{path.replace(chr(39),chr(39)*2)}')")
            connection.execute("""CREATE VIEW clean_sales AS SELECT * EXCLUDE(dedup_rank) FROM
                (SELECT *, ROW_NUMBER() OVER(PARTITION BY sales_line_id ORDER BY ingested_at) dedup_rank FROM sales_fact) WHERE dedup_rank=1""")
            connection.execute("""CREATE VIEW joined_sales AS SELECT f.*, p.product_name, m.market, c.month_label,
                f.gross_cents-f.discount_cents-f.return_cents+f.adjustment_cents net_cents
                FROM clean_sales f JOIN product_dim p USING(product_id) JOIN market_dim m USING(market_id)
                JOIN calendar_dim c USING(sale_date)""")
            connection.execute("SET allowed_paths=?",[files])
            connection.execute("SET enable_external_access=false")
            connection.execute("SET lock_configuration=true")
            yield connection
        finally:
            if connection is not None: connection.close()
            self._session_slot.release()

    def filters(self, request, scope):
        self.authorize(request,scope)
        clauses = ["market IN ("+",".join("?" for _ in scope.markets)+")"]
        params = list(scope.markets)
        for field,column in (("market","market"),("product","product_name"),("channel","channel")):
            value = getattr(request,field)
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        return " AND ".join(clauses), params

    def prepare(self, request, scope, kind="total", period="baseline", dimension="market"):
        request = SalesRequest.model_validate(request)
        if kind not in ("total","trend","breakdown") or period not in ("baseline","current") or dimension not in DIMENSIONS:
            raise ValueError("Unapproved sales query operation")
        where, params = self.filters(request,scope)
        bounds = getattr(request,period)
        grouping = {"total":"'All'", "trend":"month_label", "breakdown":DIMENSIONS[dimension]}[kind]
        sql = f"SELECT {grouping} AS group_name, {AMOUNTS} FROM joined_sales WHERE sale_date>=?::DATE AND sale_date<?::DATE AND {where}"
        if kind != "total": sql += f" GROUP BY {grouping} ORDER BY {grouping}"
        if kind == "trend":
            sql = f"""WITH spine AS (SELECT DISTINCT month_label FROM calendar_dim WHERE sale_date>=?::DATE AND sale_date<?::DATE),
                amounts AS (SELECT month_label, {AMOUNTS} FROM joined_sales WHERE sale_date>=?::DATE AND sale_date<?::DATE AND {where}
                    GROUP BY month_label)
                SELECT spine.month_label group_name, COALESCE(net_cents,0)::BIGINT net_cents,
                    COALESCE(units_sold,0)::BIGINT units_sold, COALESCE(orders,0)::BIGINT orders
                FROM spine LEFT JOIN amounts USING(month_label) ORDER BY spine.month_label"""
        bindings=[bounds.start.isoformat(),bounds.end.isoformat()]+params
        if kind == "trend": bindings=[bounds.start.isoformat(),bounds.end.isoformat()]+bindings
        return BoundSalesQuery(request=request,kind=kind,period=period,dimension=dimension,
            template=f"sales.{kind}.{request.metric}.{dimension}",sql=sql,
            parameters=tuple(bindings))

    def execute_bound(self, bound, scope):
        canonical = self.prepare(bound.request,scope,bound.kind,bound.period,bound.dimension)
        if bound != canonical: raise PermissionError("Sales query binding was modified; execution denied.")
        with self.session(bound.request.scenario) as connection:
            rows, evidence = self._execute(connection,bound.sql,list(bound.parameters),bound.template,bound.request,
                {"executed_period":getattr(bound.request,bound.period).model_dump(mode="json"),
                 "authorized_scope":scope.model_dump(mode="json"),"sql_sha256":hashlib.sha256(bound.sql.encode()).hexdigest()},
                source_names=list(SALES_TABLES[:4]))
        for row in rows:
            row["net_cents"] = row["net_cents"] or 0
            row["units_sold"] = row["units_sold"] or 0
            row["value"] = sales_value(row,bound.request.metric)
        return rows,evidence

    def knowledge(self, request, scope):
        self.authorize(request,scope)
        catalog = yaml.safe_load(Path(__file__).with_name("domains.yaml").read_text(encoding="utf-8"))["sales_catalog"]
        schemas, evidence = {}, []
        with self.session(request.scenario) as connection:
            for table in SALES_TABLES:
                rows, item = self._execute(connection,f"DESCRIBE {table}",[],f"sales.schema.{table}",request,source_names=[table])
                schemas[table] = rows
                evidence.append(item)
        manifest=json.loads((self.data_dir/"manifest.json").read_text(encoding="utf-8"))
        return {"metric":sales_definitions()[request.metric].model_dump(),"catalog":catalog,"schemas":schemas,"synthetic_manifest":manifest}, evidence

    def quality(self, request, scope):
        where, params = self.filters(request,scope)
        evidence = []
        signature = "(order_id,product_id,market_id,channel,sale_date,sale_at,units_sold,returned_units,gross_cents,discount_cents,return_cents,adjustment_cents,currency)"
        checks = f"""SELECT
            (SELECT COUNT(*) FROM information_schema.columns WHERE table_name='sales_fact'
                AND column_name IN ('units_sold','returned_units','gross_cents','discount_cents','return_cents','adjustment_cents')
                AND data_type NOT IN ('BIGINT','INTEGER','SMALLINT','TINYINT','HUGEINT','UBIGINT','UINTEGER','USMALLINT','UTINYINT')) invalid_schema,
            (SELECT COUNT(*) FROM (SELECT product_id FROM product_dim GROUP BY product_id HAVING COUNT(*)<>1))+
            (SELECT COUNT(*) FROM (SELECT market_id FROM market_dim GROUP BY market_id HAVING COUNT(*)<>1))+
            (SELECT COUNT(*) FROM (SELECT sale_date FROM calendar_dim GROUP BY sale_date HAVING COUNT(*)<>1)) invalid_keys,
            (SELECT COUNT(*) FROM clean_sales f LEFT JOIN product_dim p USING(product_id) LEFT JOIN market_dim m USING(market_id)
                LEFT JOIN calendar_dim c USING(sale_date) WHERE p.product_id IS NULL OR m.market_id IS NULL OR c.sale_date IS NULL) orphan_keys,
            (SELECT COUNT(*) FROM (SELECT sales_line_id FROM sales_fact GROUP BY sales_line_id HAVING COUNT(DISTINCT {signature})>1)) conflicting_duplicates,
            (SELECT COUNT(*) FROM (SELECT order_id FROM clean_sales GROUP BY order_id HAVING COUNT(DISTINCT (market_id,sale_date,channel))>1)) invalid_order_grain,
            (SELECT COUNT(*) FROM clean_sales WHERE units_sold<=0 OR returned_units<0 OR returned_units>units_sold
                OR sales_line_id IS NULL OR order_id IS NULL OR sale_at IS NULL OR ingested_at IS NULL OR currency IS NULL
                OR units_sold IS NULL OR returned_units IS NULL OR gross_cents IS NULL OR discount_cents IS NULL
                OR return_cents IS NULL OR adjustment_cents IS NULL
                OR gross_cents<0 OR discount_cents<0 OR discount_cents>gross_cents OR return_cents<0 OR return_cents>gross_cents-discount_cents
                OR gross_cents-discount_cents-return_cents+adjustment_cents<0 OR currency<>'USD'
                OR channel IS NULL OR channel NOT IN ('Fictional Web','Fictional Shops','Fictional Partners')
                OR DATE_TRUNC('day',sale_at)<>sale_date OR ingested_at<sale_at) invalid_values"""
        with self.session(request.scenario) as connection:
            rows, item = self._execute(connection,checks,[],"sales.quality.integrity",request,source_names=list(SALES_TABLES[:4]))
            if any(rows[0].values()): raise ValueError("Sales source grain, keys, money, or join cardinality validation failed; results withheld.")
            evidence.append(item)
            stats_sql = f"""WITH raw AS (SELECT f.*,p.product_name,m.market FROM sales_fact f JOIN product_dim p USING(product_id)
                JOIN market_dim m USING(market_id) WHERE sale_date>=?::DATE AND sale_date<?::DATE AND {where}),
                arrivals AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY sales_line_id ORDER BY ingested_at) arrival_rank FROM raw)
                SELECT COUNT(*) raw_rows, COUNT(DISTINCT sales_line_id) unique_lines,
                COUNT(DISTINCT CASE WHEN arrival_rank=1 AND ingested_at>sale_at+INTERVAL '24 hours' THEN sales_line_id END) late_lines FROM arrivals"""
            start=min(request.baseline.start,request.current.start); end=max(request.baseline.end,request.current.end)
            stats, item = self._execute(connection,stats_sql,[start,end]+params,"sales.quality.events",request,source_names=list(SALES_TABLES[:3]))
            evidence.append(item)
            coverage,item = self._execute(connection,"SELECT * FROM data_quality_status WHERE scenario=? AND period_start<? AND period_end>?",
                [request.scenario,end,start],"sales.quality.coverage",request,source_names=["data_quality_status"])
            evidence.append(item)
        complete = True
        for table in SALES_TABLES:
            for period in (request.baseline,request.current):
                cursor=period.start
                for row in sorted((r for r in coverage if r["dataset"]==table),key=lambda r:r["period_start"]):
                    a=row["period_start"].date(); b=min(row["period_end"],row["available_through"]).date()
                    if row["complete"] and a<=cursor<b: cursor=b
                if cursor<period.end: complete=False
        warnings=[]
        if not complete: warnings.append("Incomplete sales coverage: results are provisional; partial months must not be treated as complete.")
        fresh=not any((r["snapshot_as_of"]-r["loaded_at"]).days>2 or r["loaded_at"]>r["snapshot_as_of"] for r in coverage)
        if not fresh:
            warnings.append("Sales snapshot freshness validation failed.")
        if stats[0]["raw_rows"]>stats[0]["unique_lines"]:
            warnings.append(f"Removed {stats[0]['raw_rows']-stats[0]['unique_lines']:,} duplicate sales lines.")
        if stats[0]["late_lines"]: warnings.append(f"Included {stats[0]['late_lines']:,} lines arriving more than 24 hours late.")
        return {"complete":complete,"freshness_valid":fresh,"freshness_basis":"Historical synthetic snapshot 2026-10-10",
            "integrity":"passed","coverage":coverage,"events":stats[0]},warnings,evidence

    def explore(self, table, scope):
        if table not in SALES_TABLES: raise ValueError("Unapproved sales table")
        self.authorize(SalesRequest(),scope)
        if set(scope.markets)!=set(AccessScope().markets): raise PermissionError("Sales Explorer requires all-market authorization.")
        with self.session() as connection:
            schema=connection.execute(f"DESCRIBE {table}").fetchall()
            count=connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            sample=connection.execute(f"SELECT * FROM {table} LIMIT ?",[min(20,self.result_limit)]).fetchdf()
        return schema,count,sample
