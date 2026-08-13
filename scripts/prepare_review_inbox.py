import hashlib
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, "state")
QUEUE_PATH = os.path.join(STATE_DIR, "review_queue.json")
# lives next to data/new/images so a reviewer manages one folder tree
# instead of jumping between data/ and state/ (was state/review_inbox)
INBOX_DIR = os.path.join(ROOT, "data", "new", "review")
OK_DIR = os.path.join(INBOX_DIR, "ok")
NG_DIR = os.path.join(INBOX_DIR, "ng")

INSTRUCTIONS = """이미지를 열어 눈으로 확인한 뒤,
정상이면 ok 폴더로, 불량이면 ng 폴더로 이 파일을 옮기거나 복사하세요.
파일 이름은 바꿔도 됩니다 (내용으로 식별합니다).
"""


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def existing_hashes_in_inbox():
    hashes = set()
    for dirpath, _, filenames in os.walk(INBOX_DIR):
        for fname in filenames:
            if fname == "HOW_TO.txt":
                continue
            hashes.add(sha256_of_file(os.path.join(dirpath, fname)))
    return hashes


def run():
    os.makedirs(OK_DIR, exist_ok=True)
    os.makedirs(NG_DIR, exist_ok=True)
    how_to_path = os.path.join(INBOX_DIR, "HOW_TO.txt")
    if not os.path.exists(how_to_path):
        with open(how_to_path, "w", encoding="utf-8") as f:
            f.write(INSTRUCTIONS)

    with open(QUEUE_PATH, encoding="utf-8") as f:
        queue = json.load(f)

    already_in_inbox = existing_hashes_in_inbox()

    copied = 0
    for entry in queue:
        if entry["human_label"] is not None:
            continue  # already reviewed, nothing to put in the inbox

        src = os.path.join(ROOT, entry["image_path"])
        content_hash = sha256_of_file(src)
        entry["content_hash"] = content_hash  # survives rename/move, used for matching later

        if content_hash in already_in_inbox:
            continue  # already copied (and possibly already sorted) in an earlier run

        dst = os.path.join(INBOX_DIR, os.path.basename(entry["image_path"]))
        # avoid clobbering if two queue items happen to share a filename
        base, ext = os.path.splitext(dst)
        i = 1
        while os.path.exists(dst):
            dst = f"{base}_{i}{ext}"
            i += 1
        shutil.copy2(src, dst)
        already_in_inbox.add(content_hash)
        copied += 1

    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    pending = sum(1 for e in queue if e["human_label"] is None)
    print(f"Copied {copied} new image(s) into {INBOX_DIR}")
    print(f"Pending review: {pending}")
    print(f"Sort each file into: {OK_DIR}  or  {NG_DIR}")


if __name__ == "__main__":
    run()
