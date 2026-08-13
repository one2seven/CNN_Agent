import datetime
import json
import os

import joblib

from common import load_image_features

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MODELS_DIR = os.path.join(ROOT, "models")
STATE_DIR = os.path.join(ROOT, "state")

# proposed default (SPEC.md §4) — not yet confirmed in coaching (PLAN.md IC-122)
CONFIDENCE_THRESHOLD = 0.65


def current_version():
    current_path = os.path.join(MODELS_DIR, "current.txt")
    if os.path.exists(current_path):
        with open(current_path, encoding="utf-8") as f:
            return f.read().strip()
    return "model_v1"


def load_review_queue():
    path = os.path.join(STATE_DIR, "review_queue.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_review_queue(queue):
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, "review_queue.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def run(new_dir=None):
    new_dir = new_dir or os.path.join(DATA_DIR, "new")
    with open(os.path.join(new_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    version = current_version()
    clf = joblib.load(os.path.join(MODELS_DIR, f"{version}.joblib"))
    classes = list(clf.classes_)  # [0, 1] == [ok, ng]
    label_names = {0: "ok", 1: "ng"}

    queue = load_review_queue()
    queued_paths = {entry["image_path"] for entry in queue}

    inference_log = []
    added = 0
    for item in manifest:
        img_path = os.path.join(new_dir, "images", item["filename"])
        rel_path = os.path.relpath(img_path, ROOT).replace("\\", "/")
        features = load_image_features(img_path)
        proba = clf.predict_proba([features])[0]
        pred_idx = int(proba.argmax())
        predicted_label = label_names[classes[pred_idx]]
        confidence = float(proba[pred_idx])
        line_label = item["line_label"]

        inference_log.append(
            {
                "image_path": rel_path,
                "model_version": version,
                "predicted_label": predicted_label,
                "confidence": confidence,
                "line_label": line_label,
                "match": predicted_label == line_label,
            }
        )

        if predicted_label != line_label:
            reason = "mismatch"
        elif confidence < CONFIDENCE_THRESHOLD:
            reason = "low_confidence"
        else:
            continue  # confident and agrees with line QA — no review needed

        if rel_path in queued_paths:
            continue  # already queued from a previous run

        queue.append(
            {
                "image_path": rel_path,
                "model_version": version,
                "predicted_label": predicted_label,
                "confidence": confidence,
                "reason": reason,
                "human_label": None,
                "reviewed_at": None,
            }
        )
        added += 1

    save_review_queue(queue)

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, "inference_log.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"model_version": version, "run_at": datetime.datetime.now().isoformat(timespec="seconds"), "results": inference_log},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Model: {version}")
    print(f"Inferred: {len(manifest)} images")
    print(f"Added to review queue: {added} (total in queue: {len(queue)})")
    return queue


if __name__ == "__main__":
    run()
