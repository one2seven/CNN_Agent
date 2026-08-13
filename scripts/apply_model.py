import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "models")
STATE_DIR = os.path.join(ROOT, "state")
REPORTS_DIR = os.path.join(STATE_DIR, "reports")
APPROVE_PATH = os.path.join(STATE_DIR, "approve.txt")
LATEST_COMPARISON_PATH = os.path.join(REPORTS_DIR, "latest_comparison.json")
CURRENT_PATH = os.path.join(MODELS_DIR, "current.txt")

APPROVED_STATUS = "승인"
APPLIED_STATUS = "적용됨"


def read_approve_entries():
    """approve.txt: one '<report_path>: <status>' line per comparison report.

    Later lines win if a report_path appears more than once. Lines that don't
    match the format are ignored rather than erroring, since a human is
    hand-editing this file.
    """
    entries = {}
    if not os.path.exists(APPROVE_PATH):
        return entries
    with open(APPROVE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            path, status = line.rsplit(":", 1)
            entries[path.strip()] = status.strip()
    return entries


def write_approve_entries(entries):
    with open(APPROVE_PATH, "w", encoding="utf-8") as f:
        for path, status in entries.items():
            f.write(f"{path}: {status}\n")


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

    entries = read_approve_entries()
    report_path = summary["report_path"]
    status = entries.get(report_path)

    if status is None:
        raise SystemExit(
            f"REJECTED: no entry for {report_path} in state/approve.txt — "
            f"a human must mark that line '{APPROVED_STATUS}' to authorize the switch. current model unchanged"
        )
    if status != APPROVED_STATUS:
        raise SystemExit(
            f"REJECTED: {report_path} is marked '{status}' in state/approve.txt, not '{APPROVED_STATUS}' — "
            f"a human must change it to authorize the switch. current model unchanged"
        )

    with open(CURRENT_PATH, "w", encoding="utf-8") as f:
        f.write(summary["new_version"])

    entries[report_path] = APPLIED_STATUS  # one-time authorization, consumed on use
    write_approve_entries(entries)

    print(f"APPLIED: current model is now {summary['new_version']} (was {summary['old_version']})")


if __name__ == "__main__":
    run()
