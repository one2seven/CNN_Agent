import os

import numpy as np
from PIL import Image

FEATURE_SIZE = 64


def load_image_features(path):
    img = Image.open(path).convert("L").resize((FEATURE_SIZE, FEATURE_SIZE))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr.flatten()


def load_dataset(dir_path):
    X, y, paths = [], [], []
    for label, value in [("ok", 0), ("ng", 1)]:
        sub_dir = os.path.join(dir_path, label)
        if not os.path.isdir(sub_dir):
            continue
        for fname in sorted(os.listdir(sub_dir)):
            if not fname.lower().endswith(".png"):
                continue
            fpath = os.path.join(sub_dir, fname)
            X.append(load_image_features(fpath))
            y.append(value)
            paths.append(fpath)
    return np.array(X), np.array(y), paths
