"""Execute the five EVP workflows using real skills, explicitly without an LLM."""
import json
from analytics_agent.agent import AnalyticsAgent, ConversationContext, DEMOS
from analytics_agent.config import PROJECT_ROOT


def run_demos():
    agent, context, answers = AnalyticsAgent(), ConversationContext(), []
    for question in DEMOS:
        answer = agent.run(question,context,mode="demo")
        if answer.status != "ok": raise RuntimeError(f"Demo failed: {answer.message}")
        answers.append(answer)
        context = answer.context
        print(f"Demo {len(answers)} passed: {question} [{', '.join(r.skill for r in answer.results)}]")
    report = {"mode":"explicit deterministic demo","status":"pass","demonstrations":[{"question":q,"answer":a.model_dump(mode="json")} for q,a in zip(DEMOS,answers)]}
    output = PROJECT_ROOT / "reports" / "demo_results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return answers


if __name__ == "__main__": run_demos()
