# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

An agent-managed retraining loop for an OK/NG image classifier. The full design contract — problem statement,
scope (must-have / nice-to-have / out-of-scope), phase breakdown with completion criteria, and verification
gates — lives in `PLAN.md`. Read it before planning new work; it is the source of truth for what "done" means
at each phase, not this file.

Training data is synthetic by design (no real production images are available in this environment): circle
outlines rendered with PIL, OK = clean circle, NG = circle with a scratch/blob/deformation defect. This keeps
the project runnable without factory data while still exercising the full retrain → compare → approve loop.

## Commands

Python on this machine must be invoked as `py`, not `python` — the `python`/`python3` aliases resolve to a
broken Windows Store stub that prints no version and exits non-zero.

```bash
# from scripts/ (each script imports common.py as a same-directory module)
py generate_data.py   # (re)generate data/train, data/val, and data/new (+ manifest.json)
py train_model.py     # train model_v1 from data/train, evaluate on data/val, save to models/
py infer.py           # run current model over data/new, update state/review_queue.json
py prepare_review_inbox.py  # copy pending review-queue images into state/review_inbox/
py label_review_queue.py    # scan state/review_inbox/{ok,ng}/ and apply human labels back to the queue
py retrain.py --check       # report whether enough reviewed-and-unused items exist to retrain
py retrain.py               # if eligible, train the next model_v<N> on train data + reviewed items
```

`train_model.py` exposes `train(version, train_dir=None, extra_X=None, extra_y=None)` — this is the entry
point later phases (retraining on reviewed data) call into, not a new script.

## Architecture

- `data/train/{ok,ng}`, `data/val/{ok,ng}` — `val` is the fixed comparison set. It must never be mixed into
  training data or regenerated independently of `train`, or model_v1-vs-model_v2 comparisons in later phases
  stop being apples-to-apples.
- `scripts/common.py` — shared feature extraction (`load_image_features`, `load_dataset`). Any script that
  loads images for inference/training/comparison should go through this, not reimplement resizing/flattening.
- `scripts/train_model.py` — trains a RandomForest on flattened grayscale pixels, writes both the model
  (`models/<version>.joblib`) and a metadata sidecar (`models/<version>.json`: created_at, train_dir, n_train,
  val_accuracy).
- `state/` — reserved for review-queue / pending-relabel data from later phases; empty for now.

### Synthetic data generation constraint (non-obvious, do not "fix")

`generate_data.py` renders every circle at a **fixed** center and radius, varying only the defect. An earlier
version randomized position/radius by a few pixels and validation accuracy collapsed to ~60% (near chance):
the RandomForest was picking up boundary-jitter noise instead of the much smaller defect signal, since raw
pixel features have no translation invariance. Fixing position/radius first brought accuracy to ~86.7%. If you
add shape variety or jitter back, expect to also change the feature representation (e.g. edge/gradient
features instead of raw pixels) or accuracy will degrade the same way.

`ambiguous_ratio` in `generate_data.py` deliberately generates some NG images with low-severity defects. This
guarantees genuinely hard/low-confidence cases exist for the review-queue phase to collect — without it, a
well-separated synthetic dataset could yield zero misclassifications and nothing to review.

OK images additionally get per-pixel Gaussian noise (`NOISE_SIGMA`) and, at `benign_artifact_ratio`, a faint
blob identical in size to a mild NG defect but labeled OK (stand-in for dust/glare — a real part, not a real
defect). Without this, every OK image render was byte-identical (zero variance in position/radius/pixels), so
model_v1 was 100%-confident and 100%-correct on literally every OK image — the review queue could only ever
fill with NG, and PLAN.md's second error direction ("모델이 OK를 NG로 오판") was structurally unreachable. This
brought val accuracy down to ~75.8% and put some true-OK images into the review queue as genuine low-confidence
cases. Current tuning still produces zero actual OK→NG misclassifications on the val set (recall for OK stays
100%); pushing the benign-artifact size further would very likely change that, at the cost of NG recall
(already down to ~52%) — treat that as a tuning knob, not a bug, if you touch it.

### Human review is folder-based and hash-matched, not filename-matched

`state/review_inbox/{ok,ng}/` is where a person actually sorts flagged images by looking at them — no screen
needed. `label_review_queue.py` never trusts filenames: it walks both folders recursively and matches files
back to `review_queue.json` entries by sha256 content hash (`prepare_review_inbox.py` stamps this hash when it
copies a pending image in). This is deliberate, not incidental — a real reviewer renames files and drops them
in nested folders by mistake, and the matching has to survive that. It also means a file with content the
queue doesn't recognize is reported as "unknown" rather than silently ignored or crashing, and the same image
appearing in both `ok/` and `ng/` is reported as a conflict rather than resolved by picking one arbitrarily.
If you touch this matching logic, keep it hash-based — reintroducing filename matching reopens exactly the
failure mode it was built to avoid.
