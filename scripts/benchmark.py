"""Real local analytical timings and peak process memory; no LLM requests."""
import ctypes
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from analytics_agent.agent import AnalyticsAgent
from analytics_agent.config import PROJECT_ROOT
from analytics_agent.engine import Engine
from analytics_agent.models import AnalyticsRequest
from analytics_agent.skills import SkillRegistry, ToolArguments


def peak_memory_mb():
    if os.name == "nt":
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ["PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage","QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage"]]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        get_memory = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        get_memory.argtypes = [wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        success = get_memory(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb)
        return round(counters.PeakWorkingSetSize/1024**2,2) if success else None
    import resource
    import sys
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform == "darwin" else 1024),2)


def benchmark():
    engine = Engine(memory=os.getenv("DUCKDB_MEMORY_LIMIT","512MB"))
    registry = SkillRegistry(engine)
    timings = {}
    for skill in ["K1","K2","K3"]:
        result = registry.execute(skill,ToolArguments(request=AnalyticsRequest()))
        timings[skill] = {"duration_ms":result.duration_ms,"queries":len(result.evidence),"query_ms":[e.duration_ms for e in result.evidence]}
    cold_agent = AnalyticsAgent(SkillRegistry(Engine(memory=engine.memory)))
    question = "Investigate the September decline across markets and cohorts."
    answer = cold_agent.run(question,mode="demo")
    if answer.status != "ok": raise RuntimeError(answer.message)
    warm = cold_agent.run(question,mode="demo")
    if warm.status != "ok": raise RuntimeError(warm.message)
    shared_agent = AnalyticsAgent(SkillRegistry(Engine(memory=engine.memory)))
    barrier = threading.Barrier(4)
    def concurrent_request(_):
        barrier.wait(timeout=10)
        return shared_agent.run(question,mode="demo")
    with ThreadPoolExecutor(max_workers=4) as pool: concurrent = list(pool.map(concurrent_request,range(4)))
    if any(item.status != "ok" or item.results[0].current != answer.results[0].current or item.results[0].baseline != answer.results[0].baseline for item in concurrent):
        raise RuntimeError("Concurrent investigation failed or returned inconsistent totals.")
    report = {"skill_timings":timings,"end_to_end_ms":answer.elapsed_ms,"warm_end_to_end_ms":warm.elapsed_ms,"tool_calls":answer.tool_calls,"peak_process_memory_mb":peak_memory_mb(),"duckdb_memory_limit":engine.memory,"llm_latency_ms":None,
        "concurrent_requests":len(concurrent),"concurrent_passed":sum(item.status == "ok" for item in concurrent),"concurrent_elapsed_ms":[round(item.elapsed_ms,3) for item in concurrent],
        "notes":"Cold, warm and four simultaneous shared-engine investigations measured locally; not a production load test; live LLM latency unavailable."}
    path = PROJECT_ROOT / "reports" / "performance.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report


if __name__ == "__main__": print(json.dumps(benchmark(),indent=2))
