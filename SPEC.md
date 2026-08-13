# SPEC.md

이미지 학습 자동화 — 기술 명세. 요구사항·범위·완료 기준의 계약은 `PLAN.md`가 원본이고, 이 문서는 그걸
구현하기 위한 디렉토리 구조·데이터 스키마·Phase별 기술 설계를 정리한다. PLAN.md와 상충하면 PLAN.md가 우선.

## 1. 디렉토리 구조

```
data/
  train/{ok,ng}/*.png      # 고정 학습셋 (Phase 1에서 생성)
  val/{ok,ng}/*.png        # 고정 검증셋 — model_v1/v2 비교에 항상 이것만 사용
  new/
    images/*.png             # 신규 유입 이미지 시뮬레이션 (완료 — generate_new_batch), 원본이라 손대지 않음
    manifest.json             # [{filename, line_label}] — 기존 라인 QA 판정
    review/                    # 완료 (Phase 3) — 사람이 실제로 눈으로 보고 분류하는 폴더 (data/new 밑에 둬서 images/와 한 곳에서 관리, 원래 state/review_inbox였음)
      HOW_TO.txt
      <미분류 이미지>.png        # 아직 ok/ng로 안 옮긴 것
      ok/                        # 사람이 정상이라고 판단해 옮긴 이미지
      ng/                        # 사람이 불량이라고 판단해 옮긴 이미지
models/
  model_v1.joblib / model_v1.json
  model_v2.joblib / model_v2.json   # 완료 (Phase 3) — base 400장 + 리뷰 25장, val accuracy 78.3%
  current.txt                        # (Phase 4) 현재 운영 모델 버전 이름 1줄
state/
  review_queue.json         # 완료 (Phase 2, infer.py가 생성; content_hash 필드는 Phase 3에서 추가)
  inference_log.json         # 완료 — infer.py 실행마다 전체 추론 결과 기록
  approve.txt                # (Phase 4) 사람이 직접 만들어야 함 — apply_model.py가 성공 시 삭제(1회성)
  reports/
    report_<timestamp>.md      # 완료 (Phase 4) — compare_models.py가 매 실행마다 생성
    latest_comparison.json      # 완료 — apply_model.py가 읽는 구조화된 판정 결과
scripts/
  generate_data.py    # 완료 — train/val/new(manifest 포함) 모두 생성
  common.py            # 완료 — 이미지 로딩/특징 추출 공용 모듈
  train_model.py       # 완료 — train(version, train_dir, extra_X, extra_y)
  infer.py              # 완료 (Phase 2) — 신규 이미지 추론 + Review Queue 수집
  prepare_review_inbox.py  # 완료 (Phase 3) — 미판정 이미지를 data/new/review/로 복사 + content_hash 기록
  label_review_queue.py     # 완료 (Phase 3) — data/new/review/ok, ng를 스캔해 사람 판정을 review_queue.json에 반영
  retrain.py            # 완료 (Phase 3) — 트리거 판단(--check) + 사람 라벨 반영 재학습 → model_v2
  compare_models.py     # 완료 (Phase 4) — 기준 vs 후보 모델 비교 + report.md/latest_comparison.json 생성
  apply_model.py        # 완료 (Phase 4) — 판정 "적용 가능" AND approve.txt 있을 때만 current.txt 교체
```

## 2. 데이터 스키마

### `state/review_queue.json` (Phase 2에서 생성/갱신 — `infer.py`)
```json
[
  {
    "image_path": "data/new/images/new_0003.png",
    "model_version": "model_v1",
    "predicted_label": "ok",
    "confidence": 0.9,
    "reason": "mismatch",
    "human_label": null,
    "reviewed_at": null,
    "content_hash": "sha256 hex digest",
    "used_for_version": null
  }
]
```
- `reason`: `"mismatch"`(모델 판정이 기존 라인 QA 판정과 다름, 우선순위 높음) / `"low_confidence"`(둘은 같지만 confidence가 임계값 미만) / `"manual_flag"`(사용자가 직접 지정 — 미구현)
- `human_label`/`reviewed_at`은 Phase 3에서 사람이 채움. 채워진 항목만 재학습 데이터 후보가 됨.
- `content_hash`는 `prepare_review_inbox.py`가 이미지 파일 내용을 sha256으로 해시해 채운다. 사람이 `data/new/review/`에서 파일을 옮기며 이름을 바꾸거나 하위 폴더를 만들어도 내용은 그대로이므로, `label_review_queue.py`는 파일명이 아니라 이 해시로 원본 큐 항목을 다시 찾는다.
- `used_for_version`은 `retrain.py`가 그 항목을 실제로 재학습에 사용한 뒤 버전 이름(예: `"model_v2"`)으로 채운다. 이미 채워진 항목은 다음 재학습 트리거 판단에서 제외되어 중복 사용되지 않는다.
- 신규 이미지는 `data/new/manifest.json`에 `{filename, line_label}`로 나열되고, `line_label`이 위 `reason: mismatch` 판정에 쓰이는 기존 라인 QA 판정이다(`generate_data.py`의 `generate_new_batch`).

### `models/<version>.json` (Phase 1에서 구현 완료)
```json
{
  "version": "model_v1",
  "created_at": "2026-08-13T09:36:49",
  "train_dir": "data/train",
  "n_train": 400,
  "val_accuracy": 0.7583
}
```

### `state/reports/report_<timestamp>.md` (Phase 4)
최소 포함 항목:
- model_v1 vs model_v2: Accuracy, OK/NG 각각의 Precision·Recall
- 기존엔 맞았는데 신규에서 틀린 이미지 목록, 기존엔 틀렸는데 신규에서 맞은 이미지 목록
- 결론: 적용 가능 / 불가 (판정 근거 포함)

## 3. Phase별 기술 설계

### Phase 1 — 완료
`generate_data.py`로 원형 합성 OK/NG 이미지 생성(고정 위치·반경, 결함만 랜덤 — 이유는 CLAUDE.md 참고),
`train_model.py`로 `model_v1` 학습. val accuracy 75.8%(노이즈·양성 이물질 추가 이후 — §1 참고).

### Phase 2 — 추론 + Review Queue 자동 수집 (완료)
`infer.py`:
1. `models/current.txt`(없으면 `model_v1`)로 `data/new/manifest.json`에 나열된 이미지를 추론
2. 모델 예측이 `line_label`(기존 라인 QA 판정)과 다르면 `reason: mismatch`, 같지만 confidence가 임계값(제안값 0.65 — 코칭에서 확정) 미만이면 `reason: low_confidence`로 `review_queue.json`에 추가. 재실행 시 이미 큐에 있는 이미지는 중복 추가하지 않음
3. 참고용으로 전체 추론 결과(정답 비교 포함)를 `state/inference_log.json`에 남김
4. 완료 조건(PLAN.md ④): 실행 후 `review_queue.json`에 1건 이상 존재 — 40장 중 25건(mismatch 14 + low_confidence 11)으로 확인됨, 이 중 8건은 실제 OK 이미지(전부 low_confidence 경로 — §1 노이즈 추가 이후 OK도 큐에 들어올 수 있게 됨)

### Phase 3 — 사람 판정 반영 + 재학습
사람이 실제로 이미지를 열어보고 판정해야 의미가 있으므로(PLAN.md ⑥), 화면 없이 **파일 탐색기로 폴더에 옮기는 것**만으로 판정이 끝나게 설계했다.

1. `prepare_review_inbox.py`: `review_queue.json`에서 아직 `human_label`이 없는 항목의 이미지를 `data/new/review/`에 복사하고, 각 항목에 `content_hash`를 채운다. 재실행해도 이미 inbox에 있는(혹은 이미 사람이 ok/ng로 옮긴) 이미지는 다시 복사하지 않는다. `data/new/images/`(원본)는 절대 바꾸지 않는다.
2. 사람이 `data/new/review/`의 이미지를 직접 열어보고 `ok/` 또는 `ng/` 폴더로 옮기거나 복사한다. **파일 이름을 바꾸거나, 하위 폴더를 만들거나, 실수로 안 옮겨도 된다** — `label_review_queue.py`는 파일명이 아니라 `content_hash`로 원본을 식별한다(`os.walk`로 하위 폴더까지 재귀 탐색).
3. `label_review_queue.py`: `ok/`, `ng/`를 스캔해 해시가 일치하는 큐 항목에 `human_label`/`reviewed_at`을 채운다. 예외는 조용히 넘기지 않고 각각 다르게 보고한다:
   - 큐에 없는 내용의 파일(오분류/실수로 섞인 파일) → "알 수 없는 파일"로 보고하고 무시
   - 같은 이미지가 `ok/`와 `ng/` 모두에 있음(복사 실수) → "충돌"로 보고하고 라벨링하지 않음(둘 중 하나를 지우고 재실행해야 함)
   - 아직 어느 폴더에도 없음 → 그대로 pending 유지
4. `retrain.py --check`: `human_label`이 채워졌고 아직 재학습에 안 쓰인(`used_for_version`이 null인) 항목 수를 세어 READY/WAITING을 출력
5. `retrain.py`: 트리거 조건(제안값 20건 — 코칭에서 확정, IC-122) 충족 시 그 항목들을 로드해 `train_model.train(version=<다음 버전>, extra_X=..., extra_y=...)` 호출, 성공하면 사용한 항목에 `used_for_version`을 표시(중복 재사용 방지)
6. 완료 조건: `model_v2.joblib` 생성됨 — 확인됨(base 400장 + 리뷰 25장 = 425장, val accuracy 75.8%(model_v1) → 78.3%(model_v2))

### Phase 4 — 비교 + 리포트 + 승인 게이트 (완료)
- `compare_models.py`: 고정 `data/val`셋(120장)에 대해 기준 모델(기본값: `models/current.txt`, 없으면 `model_v1`)과 후보 모델(기본값: 가장 높은 버전 번호) 각각 추론 → Accuracy/OK·NG Precision·Recall 계산 → `state/reports/report_<timestamp>.md` 생성 + `state/reports/latest_comparison.json`에 구조화된 판정 결과 저장
- 적용 기준(제안값 — 코칭에서 확정, IC-122): accuracy가 낮아지지 않고, 기존엔 맞았는데 후보에서 틀리는 이미지 비율(regression rate)이 5% 이하일 때만 "적용 가능". 실측: model_v1(75.8%) → model_v2(78.3%), regression 1/120(0.8%), improvement 4장 → **적용 가능**
- `apply_model.py`: `latest_comparison.json`의 판정이 "적용 가능"이고 **동시에** `state/approve.txt`가 있을 때만 `models/current.txt`를 후보 버전으로 교체(적용 후 `approve.txt`는 삭제되어 1회성 승인으로 소비됨). 판정이 "적용 불가"면 `approve.txt`가 있어도 무조건 거부 — 사람 승인이 나쁜 모델 적용의 우회 경로가 되지 않게 함(PLAN.md '기존 모델보다 나빠지면 안 됨')

## 4. 아직 확정 안 된 것 (PLAN.md "1:1 코칭에서 가장 묻고 싶은 것" 및 "고칠 곳"과 연결)
- confidence 임계값, 재학습 트리거 개수, 적용 승인 임계치 — 위 제안값은 구현을 막지 않기 위한 기본값일 뿐, 코칭에서 조정 예정
- 망분리 환경에서 실제 이미지·판정 데이터를 Claude에게 전달하는 방법 (PLAN.md 코칭 질문) — 이 SPEC은 로컬 파일 접근을 전제로 하므로, 실제 적용 시 데이터 반입 경로 설계가 별도로 필요
