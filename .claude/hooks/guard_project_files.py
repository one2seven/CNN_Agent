import json
import os
import re
import sys

PROTECTED_FILES = {"review_queue.json", "approve.txt"}
REASONS = {
    "review_queue.json": (
        "review_queue.json은 사람이 실제로 이미지를 보고 내린 판정만 들어가야 합니다. "
        "Claude가 직접 고치는 대신 data/new/review/{ok,ng}로 이미지를 분류한 뒤 "
        "label_review_queue.py를 실행해달라고 요청하세요."
    ),
    "approve.txt": (
        "approve.txt는 운영 모델 교체를 사람이 최종 승인했다는 신호입니다 (PLAN.md ⑤). "
        "Claude가 대신 만들 수 없습니다 — 사람이 직접 만들어야 합니다."
    ),
}

# operator must appear shortly BEFORE the filename (not just anywhere in the
# same command string) — otherwise prose that merely mentions the filename
# and a word like "copy" (e.g. in a commit message) triggers a false block
WRITE_NEAR_FILE = {
    fname: re.compile(
        r"(>>?|New-Item|Set-Content|Out-File|\bcp\b|\bcopy\b|\bmv\b|\btee\b)[^\n]{0,20}?" + re.escape(fname),
        re.IGNORECASE,
    )
    for fname in ("review_queue.json", "approve.txt")
}


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    payload = json.load(sys.stdin)
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        base = os.path.basename(path.replace("\\", "/"))
        if base in PROTECTED_FILES:
            deny(REASONS[base])

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        for fname, pattern in WRITE_NEAR_FILE.items():
            if pattern.search(command):
                deny(f"쉘 명령으로 {fname}를 직접 쓰려는 것으로 보입니다. " + REASONS[fname])

    sys.exit(0)


if __name__ == "__main__":
    main()
