import datetime
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, "state")
QUEUE_PATH = os.path.join(STATE_DIR, "review_queue.json")
INBOX_DIR = os.path.join(ROOT, "data", "new", "review")  # was state/review_inbox
OK_DIR = os.path.join(INBOX_DIR, "ok")
NG_DIR = os.path.join(INBOX_DIR, "ng")


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def scan_folder(folder):
    """content_hash -> list of file paths found under folder (recursive,
    so a person nesting files into sub-folders by mistake still counts)."""
    found = {}
    if not os.path.isdir(folder):
        return found
    for dirpath, _, filenames in os.walk(folder):
        for fname in filenames:
            path = os.path.join(dirpath, fname)
            found.setdefault(sha256_of_file(path), []).append(path)
    return found


def run():
    with open(QUEUE_PATH, encoding="utf-8") as f:
        queue = json.load(f)

    pending_by_hash = {
        e["content_hash"]: e
        for e in queue
        if e["human_label"] is None and e.get("content_hash")
    }
    if not pending_by_hash:
        print("No pending items with a content_hash. Run prepare_review_inbox.py first.")
        return

    ok_hashes = scan_folder(OK_DIR)
    ng_hashes = scan_folder(NG_DIR)

    labeled, conflicts, unknown = 0, 0, 0

    for content_hash in set(ok_hashes) | set(ng_hashes):
        in_ok = content_hash in ok_hashes
        in_ng = content_hash in ng_hashes
        entry = pending_by_hash.get(content_hash)

        if entry is None:
            # a file whose content doesn't match any pending queue item — either a
            # stray file the reviewer dropped in by mistake, or an item that was
            # already labeled in a previous run. Skip, don't guess.
            for path in ok_hashes.get(content_hash, []) + ng_hashes.get(content_hash, []):
                print(f"[알 수 없는 파일] {path} — 리뷰 큐에 없거나 이미 처리됨, 무시합니다")
            unknown += 1
            continue

        if in_ok and in_ng:
            # same image content copied/moved into both bins — ambiguous, leave pending
            print(f"[충돌] {entry['image_path']} 이(가) ok와 ng 폴더 모두에 있습니다 — 하나만 남기고 다시 실행하세요")
            conflicts += 1
            continue

        label = "ok" if in_ok else "ng"
        entry["human_label"] = label
        entry["reviewed_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        labeled += 1
        found_at = (ok_hashes if in_ok else ng_hashes)[content_hash][0]
        print(f"[{label.upper()}] {entry['image_path']}  <-  {os.path.relpath(found_at, ROOT)}")

    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    still_pending = sum(1 for e in queue if e["human_label"] is None)
    print(f"\nLabeled: {labeled}, conflicts: {conflicts}, unknown files ignored: {unknown}")
    print(f"Still pending: {still_pending}")


if __name__ == "__main__":
    run()
