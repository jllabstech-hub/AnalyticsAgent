"""Two actual startups with Render flags. Never publishes a service."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from analytics_agent.config import PROJECT_ROOT


def smoke(port=8765):
    reports = PROJECT_ROOT / "reports"
    reports.mkdir(exist_ok=True)
    attempts = []
    for restart in range(2):
        with socket.socket() as check:
            check.bind(("127.0.0.1",port))
        started = time.perf_counter()
        environment = dict(os.environ,PORT=str(port),OPENAI_API_KEY="")
        command = [sys.executable,"-m","streamlit","run","app.py","--server.address","0.0.0.0","--server.port",environment["PORT"],"--server.headless","true"]
        with (reports / "startup_smoke.log").open("a",encoding="utf-8") as log:
            process = subprocess.Popen(command,cwd=PROJECT_ROOT,env=environment,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                deadline = time.perf_counter()+30
                while time.perf_counter() < deadline:
                    if process.poll() is not None: raise RuntimeError("Streamlit exited before health verification.")
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health",timeout=1) as response:
                            body = response.read().decode()
                            if response.status == 200 and body == "ok":
                                attempts.append({"restart":restart,"http_status":200,"health":body,"startup_seconds":round(time.perf_counter()-started,3)})
                                break
                    except (urllib.error.URLError,TimeoutError,OSError): time.sleep(.1)
                else: raise TimeoutError("Streamlit startup exceeded 30 seconds.")
            finally:
                if process.poll() is None:
                    if os.name == "nt": subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
                    else: process.terminate()
                process.wait(timeout=10)
    result = {"status":"pass","address":"0.0.0.0","port":port,"starts":attempts,"platform":sys.platform,"persistent_storage_required":False,"limitation":"Local Windows test with Render flags; not a hosted Linux/Render deployment."}
    (reports / "deployment_smoke.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8765)
    print(json.dumps(smoke(parser.parse_args().port),indent=2))
