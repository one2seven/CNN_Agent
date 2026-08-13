import datetime
import json
import os

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

from common import load_dataset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
MODELS_DIR = os.path.join(ROOT, "models")


def train(version, train_dir=None, extra_X=None, extra_y=None):
    train_dir = train_dir or os.path.join(DATA_DIR, "train")
    X, y, _ = load_dataset(train_dir)

    if extra_X is not None and len(extra_X) > 0:
        X = np.concatenate([X, extra_X])
        y = np.concatenate([y, extra_y])

    clf = RandomForestClassifier(n_estimators=150, random_state=42)
    clf.fit(X, y)

    val_dir = os.path.join(DATA_DIR, "val")
    Xv, yv, _ = load_dataset(val_dir)
    val_accuracy = float(accuracy_score(yv, clf.predict(Xv))) if len(Xv) else None

    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = os.path.join(MODELS_DIR, f"{version}.joblib")
    joblib.dump(clf, model_path)

    meta = {
        "version": version,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "train_dir": train_dir,
        "n_train": int(len(X)),
        "val_accuracy": val_accuracy,
    }
    meta_path = os.path.join(MODELS_DIR, f"{version}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Saved {model_path}")
    print(f"Train samples: {meta['n_train']}, Val accuracy: {val_accuracy}")
    return model_path, meta


if __name__ == "__main__":
    train(version="model_v1")
