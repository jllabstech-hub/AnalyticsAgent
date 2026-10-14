"""Approved parameterized SQL only; ephemeral connections never cross threads."""
import hashlib
import copy
import logging
import math
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from collections import OrderedDict
from pathlib import Path
import duckdb
from analytics_agent.config import PROJECT_ROOT
from analytics_agent.models import AccessScope, AnalyticsRequest, MetricValue, Period, QueryEvidence

LOGGER = logging.getLogger(__name__)
DEADLINE = ContextVar("analytics_deadline", default=None)
TABLES = ("users", "service_activity", "service_membership", "device_mapping", "market_reference", "data_quality_status")
GROUPS = {"market": "market", "device_model": "device_model", "service": "service",
          "new_existing": "CASE WHEN registered_at >= b.start_at THEN 'New' ELSE 'Existing' END",
          "registration": "strftime(registered_at, '%Y-%m')", "membership": "membership_cohort"}


class Engine:
    def __init__(self, data_dir: Path | None = None, timeout: float = 15, result_limit: int = 500, memory: str = "512MB"):
        if not math.isfinite(timeout) or timeout <= 0 or not isinstance(result_limit,int) or result_limit <= 0:
            raise ValueError("Execution timeout and row limit must be positive.")
        self.data_dir = (data_dir or PROJECT_ROOT / "data" / "synthetic").resolve()
        self.timeout, self.result_limit, self.memory = timeout, result_limit, memory
        self._cache, self._cache_lock = OrderedDict(), threading.Lock()
        # Streamlit shares this engine: one warehouse session bounds aggregate memory.
        self._session_slot = threading.RLock()

    def _cached(self, operation, request, scope, arguments, calculate):
        self.authorize(request, scope)
        if DEADLINE.get() is not None and time.perf_counter() >= DEADLINE.get():
            raise TimeoutError("Investigation deadline exceeded.")
        paths = [self.data_dir / ("incomplete" if name == "service_activity" and request.scenario == "incomplete" else "") / f"{name}.parquet" for name in TABLES]
        fingerprint = tuple((p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
        cache_request = request.model_copy(update={"metric":"mau"}) if operation in ("quality","trend") else request
        key = (operation,cache_request.model_dump_json(),scope.model_dump_json(),arguments,fingerprint,self.result_limit,self.memory)
        with self._cache_lock:
            cached = self._cache.get(key)
            result = copy.deepcopy(cached) if cached is not None else None
            if cached is not None: self._cache.move_to_end(key)
        def mark(value):
            if isinstance(value,QueryEvidence): return value.model_copy(update={"cache_hit":True,"duration_ms":0.,"parameters":{**value.parameters,**request.model_dump(mode="json")}})
            if isinstance(value,list): return [mark(x) for x in value]
            if isinstance(value,tuple): return tuple(mark(x) for x in value)
            if isinstance(value,dict): return {k:mark(v) for k,v in value.items()}
            return value
        if result is not None: return mark(result)
        remaining = min(self.timeout,DEADLINE.get()-time.perf_counter()) if DEADLINE.get() is not None else self.timeout
        if remaining <= 0 or not self._session_slot.acquire(timeout=remaining):
            raise TimeoutError("Analytics is busy or the investigation deadline expired. Retry shortly.")
        try:
            # Coalesce concurrent cache misses after the first request finishes.
            with self._cache_lock: cached = copy.deepcopy(self._cache.get(key))
            if cached is not None: return mark(cached)
            result = calculate()
            with self._cache_lock:
                self._cache[key] = copy.deepcopy(result)
                self._cache.move_to_end(key)
                while len(self._cache) > 32: self._cache.popitem(last=False)
            return result
        finally: self._session_slot.release()

    def authorize(self, request: AnalyticsRequest, scope: AccessScope):
        if not scope.markets or not scope.services:
            raise PermissionError("No authorized population.")
        if request.market and request.market not in scope.markets:
            raise PermissionError("Market outside authorized scope.")
        if request.service and request.service not in scope.services:
            raise PermissionError("Service outside authorized scope.")

    @contextmanager
    def session(self, scenario="primary"):
        if scenario not in ("primary", "incomplete"):
            raise ValueError("Unsupported scenario.")
        remaining = min(self.timeout, DEADLINE.get()-time.perf_counter()) if DEADLINE.get() is not None else self.timeout
        if remaining <= 0 or not self._session_slot.acquire(timeout=remaining):
            raise TimeoutError("Analytics is busy or the investigation deadline expired. Retry shortly.")
        connection = None
        try:
            connection = duckdb.connect(config={"threads": 1, "memory_limit": self.memory, "preserve_insertion_order": False,
                "temp_directory": "", "autoinstall_known_extensions": False, "autoload_known_extensions": False})
            files = []
            for name in TABLES:
                file = self.data_dir / ("incomplete" if name == "service_activity" and scenario == "incomplete" else "") / f"{name}.parquet"
                if not file.is_file():
                    raise FileNotFoundError(f"Synthetic dataset missing: {name}. Run python -m scripts.generate_data.")
                files.append(str(file).replace("\\", "/"))
                escaped = files[-1].replace("'", "''")
                connection.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{escaped}')")
            connection.execute("CREATE VIEW clean_events AS SELECT * EXCLUDE (dedup_rank) FROM (SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY ingested_at) dedup_rank FROM service_activity) WHERE dedup_rank=1")
            connection.execute("""CREATE VIEW valid_activity AS SELECT e.*, u.market, u.registered_at, u.activated_at,
                d.device_model, m.membership_cohort FROM clean_events e JOIN users u USING(user_id)
                JOIN service_membership m ON e.user_id=m.user_id AND e.service=m.service
                    AND e.event_at>=m.eligible_from AND e.event_at<m.eligible_to
                JOIN device_mapping d ON e.user_id=d.user_id AND e.device_id=d.device_id
                    AND e.event_at>=d.valid_from AND e.event_at<d.valid_to
                WHERE e.event_at>=u.activated_at""")
            connection.execute("SET allowed_paths = ?", [files])
            connection.execute("SET enable_external_access=false")
            connection.execute("SET lock_configuration=true")
            yield connection
        finally:
            if connection is not None: connection.close()
            self._session_slot.release()

    def _execute(self, connection, sql, params, template, request, execution=None):
        if not sql.lstrip().upper().startswith(("SELECT", "WITH", "DESCRIBE")) or ";" in sql:
            raise ValueError("Only internal read-only templates are accepted.")
        started = time.perf_counter()
        remaining = DEADLINE.get() - started if DEADLINE.get() is not None else self.timeout
        if remaining <= 0:
            raise TimeoutError("Investigation deadline exceeded.")
        timer = threading.Timer(min(self.timeout, remaining), connection.interrupt)
        timer.daemon = True
        timer.start()
        try:
            cursor = connection.execute(sql, params)
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchmany(self.result_limit + 1)
            if len(rows) > self.result_limit:
                raise ValueError("Result exceeds configured limit.")
        except Exception as error:
            LOGGER.warning("template=%s failed=%s",template,type(error).__name__)
            raise
        finally:
            timer.cancel()
            timer.join()
        duration = (time.perf_counter() - started) * 1000
        source_map = {"quality.coverage":["data_quality_status"],"quality.events":["service_activity","users","device_mapping"],
            "quality.temporal_keys":["users","service_activity","service_membership","device_mapping","market_reference"],"quality.source_grain":["service_activity"],
            "quality.conflicting_duplicates":["service_activity"]}
        sources = source_map.get(template,["users","service_activity","service_membership","device_mapping"])
        if template.startswith(("metric.new_users.","metric.activation_rate.")):
            sources = ["users","service_membership","device_mapping"]
        evidence = QueryEvidence(query_id=hashlib.sha256((template + str(params)).encode()).hexdigest()[:16],
            template=template, duration_ms=round(duration, 3), rows=len(rows), parameters={**request.model_dump(mode="json"), **(execution or {})}, sources=sources)
        LOGGER.info("template=%s rows=%d duration_ms=%.2f", template, len(rows), duration)
        return [dict(zip(columns, row)) for row in rows], evidence

    def _filters(self, request, scope):
        self.authorize(request, scope)
        clauses = ["market IN (" + ",".join("?" for _ in scope.markets) + ")", "service IN (" + ",".join("?" for _ in scope.services) + ")"]
        params = list(scope.markets) + list(scope.services)
        for column in ("market", "service", "device_model"):
            value = getattr(request, column)
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        return " AND ".join(clauses), params

    def metric(self, request: AnalyticsRequest, period: Period, scope: AccessScope = AccessScope(), group_by=None):
        return self._cached("metric",request,scope,(period.model_dump_json(),group_by),lambda:self._metric(request,period,scope,group_by))

    def _metric(self, request, period, scope, group_by):
        if group_by is not None and group_by not in GROUPS:
            raise ValueError("Unsupported dimension or cohort.")
        where, params = self._filters(request, scope)
        label = GROUPS[group_by] if group_by else "'All'"
        # Adoption uses associations overlapping the period, as its numerator does.
        device_end = ("greatest(d.valid_from,m.eligible_from,u.registered_at,b.start_at)<least(d.valid_to,m.eligible_to,b.end_at)"
            if request.metric == "service_adoption_rate" else "d.valid_to>=b.end_at")
        base = f"""WITH bounds AS (SELECT ?::TIMESTAMP start_at, ?::TIMESTAMP end_at),
            active AS (SELECT a.* FROM valid_activity a, bounds b WHERE event_at>=b.start_at AND event_at<b.end_at AND {where}),
            population AS (SELECT u.*, m.service, m.membership_cohort, d.device_model FROM users u
                JOIN service_membership m USING(user_id) JOIN device_mapping d USING(user_id), bounds b
                WHERE m.eligible_from<b.end_at AND m.eligible_to>b.start_at AND u.registered_at<b.end_at
                AND d.valid_from<b.end_at AND {device_end} AND {where})"""
        # Filter values occur in each independently parameterized population.
        parameters = [period.start, period.end] + params + params
        metric = request.metric
        if metric == "dau":
            sql = base + f", daily AS (SELECT {label} grp, CAST(event_at AS DATE) AS activity_day, count(DISTINCT user_id) n FROM active, bounds b GROUP BY 1,2) SELECT grp, sum(n)::DOUBLE/date_diff('day', b.start_at,b.end_at) numerator, NULL::DOUBLE denominator FROM daily, bounds b GROUP BY grp,b.start_at,b.end_at"
        elif metric in ("mau", "active_existing_users"):
            condition = "WHERE registered_at<b.start_at" if metric == "active_existing_users" else ""
            sql = base + f" SELECT {label} grp, count(DISTINCT user_id)::DOUBLE numerator, NULL::DOUBLE denominator FROM active, bounds b {condition} GROUP BY 1"
        elif metric == "new_users":
            sql = base + f" SELECT {label} grp, count(DISTINCT user_id)::DOUBLE numerator, NULL::DOUBLE denominator FROM population, bounds b WHERE registered_at>=b.start_at GROUP BY 1"
        else:
            if metric == "activation_rate":
                sql = base + f" SELECT {label} grp, count(DISTINCT user_id) FILTER (WHERE activated_at>=b.start_at AND activated_at<b.end_at)::DOUBLE numerator, count(DISTINCT user_id)::DOUBLE denominator FROM population, bounds b WHERE registered_at>=b.start_at GROUP BY 1"
            else:
                sql = base + f", numer AS (SELECT {label} grp, count(DISTINCT user_id)::DOUBLE n FROM active, bounds b GROUP BY 1), denom AS (SELECT {label} grp, count(DISTINCT user_id)::DOUBLE d FROM population, bounds b GROUP BY 1) SELECT denom.grp, coalesce(n,0) numerator, d denominator FROM denom LEFT JOIN numer USING(grp)"
        with self.session(request.scenario) as connection:
            rows, evidence = self._execute(connection, sql, parameters, f"metric.{metric}.{group_by or 'total'}", request,
                {"executed_period":period.model_dump(mode="json"),"group_by":group_by,"authorized_scope":scope.model_dump(mode="json")})
        if not rows and group_by is None:
            rows = [{"grp": "All", "numerator": 0., "denominator": 0. if metric.endswith("rate") else None}]
        values = [MetricValue(group=r["grp"], numerator=r["numerator"], denominator=r["denominator"], value=(r["numerator"] / r["denominator"] if r["denominator"] else None) if metric.endswith("rate") else r["numerator"]) for r in rows]
        return values, evidence

    def trend(self, request, period, scope=AccessScope()):
        return self._cached("trend",request,scope,period.model_dump_json(),lambda:self._trend(request,period,scope))

    def _trend(self, request, period, scope):
        where, params = self._filters(request, scope)
        sql = f"""WITH bounds AS (SELECT ?::DATE start_at, ?::DATE end_at),
            calendar AS (SELECT CAST(day AS DATE) activity_day FROM bounds,
                generate_series(start_at,end_at-INTERVAL '1 day',INTERVAL '1 day') dates(day)),
            daily AS (SELECT CAST(event_at AS DATE) activity_day,count(DISTINCT user_id) active_users
                FROM valid_activity,bounds WHERE event_at>=start_at AND event_at<end_at AND {where} GROUP BY 1)
            SELECT c.activity_day, CASE WHEN EXISTS(SELECT 1 FROM data_quality_status q
                WHERE q.scenario=? AND q.dataset='service_activity' AND c.activity_day>=q.period_start
                AND c.activity_day+INTERVAL '1 day'<=least(q.period_end,q.available_through))
                THEN coalesce(d.active_users,0) ELSE NULL END active_users
            FROM calendar c LEFT JOIN daily d USING(activity_day) ORDER BY 1"""
        with self.session(request.scenario) as connection:
            rows, evidence = self._execute(connection, sql, [period.start, period.end] + params + [request.scenario], "trend.dau", request,
                {"executed_period":period.model_dump(mode="json"),"authorized_scope":scope.model_dump(mode="json")})
            return rows, evidence.model_copy(update={"sources":evidence.sources+["data_quality_status"]})

    def quality(self, request, scope=AccessScope()):
        return self._cached("quality",request,scope,None,lambda:self._quality(request,scope))

    def _quality(self, request, scope):
        self.authorize(request, scope)
        start, end = min(request.baseline.start, request.current.start), max(request.baseline.end, request.current.end)
        with self.session(request.scenario) as connection:
            quality, evidence = self._execute(connection, "SELECT dataset,period_start,period_end,complete,available_through,loaded_at,snapshot_as_of,status FROM data_quality_status WHERE scenario=? AND period_start<? AND period_end>?", [request.scenario, end, start], "quality.coverage", request)
            where, params = self._filters(request, scope)
            stats, stats_evidence = self._execute(connection, f"SELECT count(*) raw_rows,count(DISTINCT event_id) unique_events,count(DISTINCT event_id) FILTER(WHERE ingested_at>event_at+INTERVAL '24 hours') late_events FROM service_activity e JOIN users u USING(user_id) JOIN device_mapping d ON e.user_id=d.user_id AND e.device_id=d.device_id AND e.event_at>=d.valid_from AND e.event_at<d.valid_to WHERE event_at>=? AND event_at<? AND {where}", [start, end]+params, "quality.events", request)
            keys, key_evidence = self._execute(connection, """SELECT sum(violations) violations FROM (
                SELECT count(*)-count(DISTINCT user_id) violations FROM users
                UNION ALL SELECT count(*) FROM users WHERE activated_at<registered_at OR market NOT IN(SELECT market FROM market_reference)
                UNION ALL SELECT count(*) FROM service_membership WHERE eligible_from>=eligible_to
                UNION ALL SELECT count(*) FROM device_mapping WHERE valid_from>=valid_to
                UNION ALL SELECT count(*) FROM service_activity WHERE ingested_at<event_at
                UNION ALL SELECT count(*) FROM service_membership m WHERE NOT EXISTS(SELECT 1 FROM users u WHERE u.user_id=m.user_id)
                UNION ALL SELECT count(*) FROM device_mapping d WHERE NOT EXISTS(SELECT 1 FROM users u WHERE u.user_id=d.user_id)
                UNION ALL SELECT count(*) FROM (SELECT eligible_to,lead(eligible_from) OVER(PARTITION BY user_id,service ORDER BY eligible_from) next_start FROM service_membership) WHERE eligible_to>next_start
                UNION ALL SELECT count(*) FROM (SELECT valid_to,lead(valid_from) OVER(PARTITION BY user_id ORDER BY valid_from) next_start FROM device_mapping) WHERE valid_to>next_start)""", [], "quality.temporal_keys", request)
            # Separate streaming counts avoid holding two million-event hash sets at once.
            source, source_evidence = self._execute(connection, "SELECT count(DISTINCT event_id) source_events FROM service_activity", [], "quality.source_grain", request)
            matched, join_evidence = self._execute(connection, "SELECT count(*) matched_rows FROM valid_activity", [], "quality.join_cardinality", request)
            conflicts, conflict_evidence = self._execute(connection,"""WITH duplicated AS (
                SELECT event_id FROM service_activity GROUP BY event_id HAVING count(*)>1)
                SELECT count(*) conflicts FROM (SELECT e.event_id FROM service_activity e JOIN duplicated USING(event_id)
                GROUP BY e.event_id HAVING count(DISTINCT (user_id,device_id,service,event_at))>1)""",[],"quality.conflicting_duplicates",request)
            if conflicts[0]["conflicts"]:
                raise ValueError("Conflicting duplicate events detected; analytics withheld.")
            if keys[0]["violations"] or matched[0]["matched_rows"] != source[0]["source_events"]:
                raise ValueError("Join-cardinality or temporal validity failed; analytics withheld.")
        stats[0]["join_cardinality"] = "pass"
        return quality, stats[0], [evidence, stats_evidence, key_evidence, source_evidence, join_evidence,conflict_evidence]

    def explore(self, table, scope=AccessScope()):
        if table not in TABLES:
            raise ValueError("Unknown dataset.")
        full = AccessScope()
        if set(scope.markets) != set(full.markets) or set(scope.services) != set(full.services):
            raise PermissionError("Data Explorer requires full synthetic demo scope.")
        with self.session() as connection:
            schema = connection.execute(f"DESCRIBE {table}").fetchall()
            count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            sample = connection.execute(f"SELECT * FROM {table} LIMIT {min(10,self.result_limit)}").fetchdf()
        return schema, count, sample
