import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "models")
STATE_DIR = os.path.join(ROOT, "state")
REPORTS_DIR = os.path.join(STATE_DIR, "reports")
APPROVE_PATH = os.path.join(STATE_DIR, "approve.txt")
LATEST_COMPARISON_PATH = os.path.join(REPORTS_DIR, "latest_comparison.json")
CURRENT_PATH = os.path.join(MODELS_DIR, "current.txt")


def run():
    if not os.path.exists(LATEST_COMPARISON_PATH):
        raise SystemExit("REJECTED: no comparison report found — run compare_models.py first")

    with open(LATEST_COMPARISON_PATH, encoding="utf-8") as f:
        summary = json.load(f)

    # never trust approve.txt alone — a worse candidate must be refused even
    # if someone creates approve.txt anyway (PLAN.md '기존 모델보다 나빠지면 안 됨')
    if not summary["approved"]:
        raise SystemExit(
            f"REJECTED: {summary['new_version']} did not pass the comparison bar "
            f"(see {summary['report_path']}) — current model unchanged"
        )

    if not os.path.exists(APPROVE_PATH):
        raise SystemExit(
            f"REJECTED: {summary['new_version']} passed comparison but state/approve.txt is missing — "
            f"a human must create it to authorize the switch. current model unchanged"
        )

    with open(CURRENT_PATH, "w", encoding="utf-8") as f:
        f.write(summary["new_version"])

    os.remove(APPROVE_PATH)  # one-time authorization, consumed on use

    print(f"APPLIED: current model is now {summary['new_version']} (was {summary['old_version']})")


if __name__ == "__main__":
    run()
