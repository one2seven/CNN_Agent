import math
import os
import random

from PIL import Image, ImageDraw

random.seed(42)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

IMG_SIZE = 128
# single shape type keeps shape-choice from swamping the (much smaller) defect signal
SHAPES = ["circle"]


def draw_shape(draw, shape, cx, cy, r, deform=0.0):
    if shape == "circle":
        if deform <= 0:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="black", width=3)
        else:
            n = 24
            pts = []
            for i in range(n):
                ang = 2 * math.pi * i / n
                rr = r * (1 + random.uniform(-deform, deform))
                pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
            draw.polygon(pts, outline="black", width=3)
    else:
        if deform <= 0:
            draw.rectangle([cx - r, cy - r, cx + r, cy + r], outline="black", width=3)
        else:
            pts = [
                (cx - r + random.uniform(-deform, deform) * r, cy - r + random.uniform(-deform, deform) * r),
                (cx + r + random.uniform(-deform, deform) * r, cy - r + random.uniform(-deform, deform) * r),
                (cx + r + random.uniform(-deform, deform) * r, cy + r + random.uniform(-deform, deform) * r),
                (cx - r + random.uniform(-deform, deform) * r, cy + r + random.uniform(-deform, deform) * r),
            ]
            draw.polygon(pts, outline="black", width=3)


def add_scratch(draw, cx, cy, r, length_scale=1.0):
    x1 = cx + random.uniform(-r, r)
    y1 = cy + random.uniform(-r, r)
    ang = random.uniform(0, 2 * math.pi)
    length = r * 0.8 * length_scale
    x2 = x1 + length * math.cos(ang)
    y2 = y1 + length * math.sin(ang)
    draw.line([x1, y1, x2, y2], fill="black", width=random.choice([1, 2]))


def add_blob(draw, cx, cy, r, size_scale=1.0):
    bx = cx + random.uniform(-r * 0.6, r * 0.6)
    by = cy + random.uniform(-r * 0.6, r * 0.6)
    br = max(1.0, r * 0.15 * size_scale)
    draw.ellipse([bx - br, by - br, bx + br, by + br], fill="gray")


def make_image(label, ambiguous=False):
    img = Image.new("L", (IMG_SIZE, IMG_SIZE), color=255)
    draw = ImageDraw.Draw(img)
    shape = random.choice(SHAPES)
    # fixed position/radius: boundary jitter would otherwise dominate pixel
    # variance and swamp the (much smaller) defect signal a RF classifier needs
    cx = IMG_SIZE // 2
    cy = IMG_SIZE // 2
    r = 40

    if label == "ok":
        draw_shape(draw, shape, cx, cy, r, deform=0.0)
    else:
        # ambiguous NG uses a smaller defect severity so it's genuinely hard to call
        severity = random.uniform(0.15, 0.35) if ambiguous else random.uniform(0.5, 1.0)
        defect = random.choice(["scratch", "blob", "deform"])
        if defect == "scratch":
            draw_shape(draw, shape, cx, cy, r, deform=0.0)
            add_scratch(draw, cx, cy, r, length_scale=severity * 1.2)
        elif defect == "blob":
            draw_shape(draw, shape, cx, cy, r, deform=0.0)
            add_blob(draw, cx, cy, r, size_scale=severity * 1.5)
        else:
            draw_shape(draw, shape, cx, cy, r, deform=severity * 0.3)
    return img


def generate_set(out_dir, n_ok, n_ng, ambiguous_ratio=0.0, prefix=""):
    ok_dir = os.path.join(out_dir, "ok")
    ng_dir = os.path.join(out_dir, "ng")
    os.makedirs(ok_dir, exist_ok=True)
    os.makedirs(ng_dir, exist_ok=True)
    for i in range(n_ok):
        img = make_image("ok")
        img.save(os.path.join(ok_dir, f"{prefix}ok_{i:04d}.png"))
    for i in range(n_ng):
        ambiguous = random.random() < ambiguous_ratio
        img = make_image("ng", ambiguous=ambiguous)
        img.save(os.path.join(ng_dir, f"{prefix}ng_{i:04d}.png"))


if __name__ == "__main__":
    train_dir = os.path.join(DATA_DIR, "train")
    val_dir = os.path.join(DATA_DIR, "val")
    # ambiguous_ratio guarantees some low-confidence / hard cases exist,
    # which Phase 2's review-queue collection depends on (see PLAN.md 고칠 곳 #2)
    generate_set(train_dir, n_ok=200, n_ng=200, ambiguous_ratio=0.25)
    generate_set(val_dir, n_ok=60, n_ng=60, ambiguous_ratio=0.25)
    print("Generated train: 200 ok + 200 ng, val: 60 ok + 60 ng")
