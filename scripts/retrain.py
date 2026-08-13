import argparse
import glob
import json
import os
import re

import numpy as np

from common import load_image_features
from train_model import train

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, "state")
MODELS_DIR = os.path.join(ROOT, "models")
QUEUE_PATH = os.path.join(STATE_DIR, "review_queue.json")

# proposed default (SPEC.md §3 Phase 3) — not yet confirmed in coaching (PLAN.md IC-122)
RETRAIN_TRIGGER_COUNT = 20


def load_queue():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def unused_reviewed_entries(queue):
    return [e for e in queue if e["human_label"] is not None and e.get("used_for_version") is None]


def next_version():
    existing = glob.glob(os.path.join(MODELS_DIR, "model_v*.joblib"))
    numbers = []
    for path in existing:
        m = re.search(r"model_v(\d+)\.joblib$", path)
        if m:
            numbers.append(int(m.group(1)))
    return f"model_v{max(numbers) + 1}" if numbers else "model_v1"


def check_trigger(queue):
    pending = unused_reviewed_entries(queue)
    eligible = len(pending) >= RETRAIN_TRIGGER_COUNT
    print(f"Reviewed-and-unused items: {len(pending)} (trigger threshold: {RETRAIN_TRIGGER_COUNT})")
    print("Status: READY to retrain" if eligible else f"Status: WAITING (need {RETRAIN_TRIGGER_COUNT - len(pending)} more)")
    return pending, eligible


def run_retrain():
    queue = load_queue()
    pending, eligible = check_trigger(queue)
    if not eligible:
        return None

    extra_X, extra_y = [], []
    label_to_int = {"ok": 0, "ng": 1}
    for entry in pending:
        img_path = os.path.join(ROOT, entry["image_path"])
        extra_X.append(load_image_features(img_path))
        extra_y.append(label_to_int[entry["human_label"]])
    extra_X = np.array(extra_X)
    extra_y = np.array(extra_y)

    version = next_version()
    model_path, meta = train(version=version, extra_X=extra_X, extra_y=extra_y)

    for entry in pending:
        entry["used_for_version"] = version
    save_queue(queue)

    print(f"\nTrained {version} on {meta['n_train']} images "
          f"(base train set + {len(pending)} reviewed images), val_accuracy={meta['val_accuracy']}")
    return model_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check retrain trigger and optionally retrain on reviewed data.")
    parser.add_argument("--check", action="store_true", help="only report trigger status, do not train")
    args = parser.parse_args()
    if args.check:
        check_trigger(load_queue())
    else:
        run_retrain()
