import argparse
import datetime
import glob
import json
import os
import re

import joblib
from sklearn.metrics import precision_recall_fscore_support

from common import load_dataset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MODELS_DIR = os.path.join(ROOT, "models")
STATE_DIR = os.path.join(ROOT, "state")
REPORTS_DIR = os.path.join(STATE_DIR, "reports")
APPROVE_PATH = os.path.join(STATE_DIR, "approve.txt")

LABEL_NAMES = {0: "ok", 1: "ng"}

# proposed defaults (SPEC.md §3 Phase 4) — not yet confirmed in coaching (PLAN.md IC-122)
MAX_REGRESSION_RATE = 0.05


def latest_version():
    existing = glob.glob(os.path.join(MODELS_DIR, "model_v*.joblib"))
    numbers = []
    for path in existing:
        m = re.search(r"model_v(\d+)\.joblib$", path)
        if m:
            numbers.append(int(m.group(1)))
    if not numbers:
        raise SystemExit("no models found in models/")
    return f"model_v{max(numbers)}"


def current_version():
    current_path = os.path.join(MODELS_DIR, "current.txt")
    if os.path.exists(current_path):
        with open(current_path, encoding="utf-8") as f:
            return f.read().strip()
    return "model_v1"


def metrics_for(clf, X, y):
    pred = clf.predict(X)
    precision, recall, _, _ = precision_recall_fscore_support(y, pred, labels=[0, 1], zero_division=0)
    accuracy = float((pred == y).mean())
    return {
        "accuracy": accuracy,
        "ok_precision": float(precision[0]),
        "ok_recall": float(recall[0]),
        "ng_precision": float(precision[1]),
        "ng_recall": float(recall[1]),
    }, pred


def run(old_version=None, new_version=None):
    old_version = old_version or current_version()
    new_version = new_version or latest_version()
    if old_version == new_version:
        raise SystemExit(f"old and new version are the same ({old_version}) — nothing to compare")

    old_clf = joblib.load(os.path.join(MODELS_DIR, f"{old_version}.joblib"))
    new_clf = joblib.load(os.path.join(MODELS_DIR, f"{new_version}.joblib"))

    X, y, paths = load_dataset(os.path.join(DATA_DIR, "val"))
    rel_paths = [os.path.relpath(p, ROOT).replace("\\", "/") for p in paths]

    old_metrics, old_pred = metrics_for(old_clf, X, y)
    new_metrics, new_pred = metrics_for(new_clf, X, y)

    regressions = [rel_paths[i] for i in range(len(y)) if old_pred[i] == y[i] and new_pred[i] != y[i]]
    improvements = [rel_paths[i] for i in range(len(y)) if old_pred[i] != y[i] and new_pred[i] == y[i]]
    regression_rate = len(regressions) / len(y)

    accuracy_ok = new_metrics["accuracy"] >= old_metrics["accuracy"]
    regression_ok = regression_rate <= MAX_REGRESSION_RATE
    approved = accuracy_ok and regression_ok

    verdict = "적용 가능" if approved else "적용 불가"
    reasons = []
    if not accuracy_ok:
        reasons.append(f"accuracy가 낮아짐 ({old_metrics['accuracy']:.4f} -> {new_metrics['accuracy']:.4f})")
    if not regression_ok:
        reasons.append(f"regression 비율 {regression_rate:.1%}이 허용 기준 {MAX_REGRESSION_RATE:.0%} 초과")
    if not reasons:
        reasons.append(f"accuracy 유지/개선, regression 비율 {regression_rate:.1%} <= {MAX_REGRESSION_RATE:.0%}")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.datetime.now()
    report_path = os.path.join(REPORTS_DIR, f"report_{timestamp.strftime('%Y%m%d_%H%M%S')}.md")

    lines = [
        f"# 모델 비교 리포트: {old_version} vs {new_version}",
        "",
        f"생성 시각: {timestamp.isoformat(timespec='seconds')}",
        f"검증셋: data/val ({len(y)}장, 고정)",
        "",
        "## 지표",
        "",
        "| 지표 | " + old_version + " | " + new_version + " |",
        "|---|---|---|",
        f"| Accuracy | {old_metrics['accuracy']:.4f} | {new_metrics['accuracy']:.4f} |",
        f"| OK Precision | {old_metrics['ok_precision']:.4f} | {new_metrics['ok_precision']:.4f} |",
        f"| OK Recall | {old_metrics['ok_recall']:.4f} | {new_metrics['ok_recall']:.4f} |",
        f"| NG Precision | {old_metrics['ng_precision']:.4f} | {new_metrics['ng_precision']:.4f} |",
        f"| NG Recall | {old_metrics['ng_recall']:.4f} | {new_metrics['ng_recall']:.4f} |",
        "",
        f"## 기존엔 맞았는데 {new_version}에서 틀린 이미지 ({len(regressions)}장)",
        "",
    ]
    lines += [f"- {p}" for p in regressions] if regressions else ["(없음)"]
    lines += [
        "",
        f"## 기존엔 틀렸는데 {new_version}에서 맞게 된 이미지 ({len(improvements)}장)",
        "",
    ]
    lines += [f"- {p}" for p in improvements] if improvements else ["(없음)"]
    lines += [
        "",
        "## 결론",
        "",
        f"**{verdict}**",
        "",
        *[f"- {r}" for r in reasons],
        "",
        f"(판정 기준은 제안값 — SPEC.md §4, 코칭에서 확정 예정. accuracy 저하 없음 AND regression 비율 <= {MAX_REGRESSION_RATE:.0%})",
        "",
        "적용하려면 state/approve.txt에서 이 리포트에 해당하는 줄을 '승인'으로 바꾼 뒤 apply_model.py를 실행해야 합니다 "
        "(사람이 직접 상태를 바꾸지 않으면 자동 적용되지 않음).",
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    summary = {
        "old_version": old_version,
        "new_version": new_version,
        "generated_at": timestamp.isoformat(timespec="seconds"),
        "old_metrics": old_metrics,
        "new_metrics": new_metrics,
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
        "regression_rate": regression_rate,
        "approved": approved,
        "report_path": os.path.relpath(report_path, ROOT).replace("\\", "/"),
    }
    with open(os.path.join(REPORTS_DIR, "latest_comparison.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with open(APPROVE_PATH, "a", encoding="utf-8") as f:
        f.write(f"{summary['report_path']}: 대기\n")

    print(f"{old_version} accuracy={old_metrics['accuracy']:.4f}  {new_version} accuracy={new_metrics['accuracy']:.4f}")
    print(f"Regressions: {len(regressions)} ({regression_rate:.1%})  Improvements: {len(improvements)}")
    print(f"Verdict: {verdict}")
    print(f"Report: {report_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two model versions on the fixed val set.")
    parser.add_argument("--old", help="baseline version (default: models/current.txt or model_v1)")
    parser.add_argument("--new", help="candidate version (default: highest model_vN found)")
    args = parser.parse_args()
    run(old_version=args.old, new_version=args.new)
