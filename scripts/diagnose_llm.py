"""Read-only diagnostics; never installs software or pulls a model."""
import argparse
import json
import shutil
import subprocess
from analytics_agent.config import load_settings
from analytics_agent.providers import OllamaProvider, ProviderError


def diagnose(inference=False):
    settings = load_settings()
    report = {"ollama_executable": shutil.which("ollama"), "configured_model": settings.ollama_model,
              "recommended_smaller_model": "qwen3:1.7b", "inference_verified": False}
    gpu = shutil.which("nvidia-smi")
    if gpu:
        result = subprocess.run([gpu, "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
        report["gpu"] = result.stdout.strip() if result.returncode == 0 else "GPU diagnostics unavailable"
    else:
        report["gpu"] = "nvidia-smi unavailable; GPU acceleration unverified"
    try:
        provider = OllamaProvider(settings.ollama_base_url, settings.ollama_model, min(settings.llm_timeout, 10), settings.ollama_api_token)
        report.update(provider.test_connection() if inference else provider.health())
    except (ProviderError, ValueError) as error:
        report.update({"reachable": False, "warning": str(error)})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", action="store_true", help="Attempt one real LOCAL model inference")
    print(json.dumps(diagnose(parser.parse_args().inference), indent=2))
