# CLAUDE.md

이 파일은 이 저장소에서 작업할 때 Claude Code(claude.ai/code)에게 제공하는 가이드입니다.

## 프로젝트

OK/NG 이미지 분류기를 위한 에이전트 관리형 재학습 루프입니다. 문제 정의, 범위(반드시 / 되면 좋은 / 안 하는 것),
Phase별 완료 기준, 검증 게이트를 포함한 전체 설계 계약은 `PLAN.md`에 있습니다. 새 작업을 계획하기 전에 반드시
읽으세요 — 각 Phase에서 "완료"가 무엇을 의미하는지에 대한 근거는 이 파일이 아니라 `PLAN.md`입니다.

학습 데이터는 의도적으로 합성 데이터입니다(이 환경에는 실제 생산 이미지가 없음): PIL로 렌더링한 원형 윤곽선이며,
OK = 깨끗한 원, NG = 흠집/얼룩/찌그러짐 결함이 있는 원입니다. 이렇게 하면 실제 공장 데이터 없이도 재학습 → 비교 →
승인 루프 전체를 구동해볼 수 있습니다.

## 명령어

이 컴퓨터에서 Python은 `python`이 아니라 반드시 `py`로 실행해야 합니다 — `python`/`python3` 별칭은 버전을
출력하지 않고 비정상 종료하는 깨진 Windows Store 스텁으로 연결됩니다.

```bash
# scripts/ 디렉터리에서 실행 (각 스크립트는 같은 디렉터리의 common.py를 모듈로 임포트함)
py generate_data.py   # data/train, data/val, data/new(+ manifest.json)를 (재)생성
py train_model.py     # data/train으로 model_v1을 학습하고 data/val로 평가, models/에 저장
py infer.py            # 현재 모델로 data/new를 추론하고 state/review_queue.json 갱신
py prepare_review_inbox.py  # 대기 중인 review-queue 이미지를 data/new/review/로 복사
py label_review_queue.py    # data/new/review/{ok,ng}/를 스캔해 사람 라벨을 큐에 반영
py retrain.py --check       # 재학습에 쓸 만큼 검토됐지만 아직 미사용인 항목이 충분한지 확인
py retrain.py               # 조건이 충족되면 학습 데이터 + 검토된 항목으로 다음 model_v<N>을 학습
py compare_models.py        # 현재 모델과 가장 높은 model_vN을 data/val로 비교하고 리포트 + latest_comparison.json 작성
py apply_model.py           # 승인됐고 state/approve.txt가 있을 때만 models/current.txt를 후보 버전으로 전환
```

`train_model.py`는 `train(version, train_dir=None, extra_X=None, extra_y=None)`을 노출합니다 — 이후 Phase
(검토된 데이터로 재학습)가 새 스크립트를 만드는 대신 호출하는 진입점입니다.

## 아키텍처

- `data/train/{ok,ng}`, `data/val/{ok,ng}` — `val`은 고정된 비교용 데이터셋입니다. 절대 학습 데이터에 섞거나
  `train`과 독립적으로 재생성해서는 안 됩니다. 그렇게 하면 이후 Phase의 model_v1 대 model_v2 비교가 더 이상
  공정한 비교가 아니게 됩니다.
- `scripts/common.py` — 공용 특징 추출 모듈(`load_image_features`, `load_dataset`). 추론/학습/비교를 위해
  이미지를 불러오는 스크립트는 모두 리사이즈·평탄화 로직을 새로 구현하지 말고 이 모듈을 거쳐야 합니다.
- `scripts/train_model.py` — 평탄화된 그레이스케일 픽셀로 RandomForest를 학습하고, 모델(`models/<version>.joblib`)과
  메타데이터 사이드카(`models/<version>.json`: created_at, train_dir, n_train, val_accuracy)를 함께 씁니다.
- `state/` — 이후 Phase의 review-queue / 재라벨 대기 데이터를 위해 예약된 공간입니다. 지금은 비어 있습니다.

### 합성 데이터 생성의 제약 조건 (비명백함, "고치지" 말 것)

`generate_data.py`는 모든 원을 **고정된** 중심·반지름으로 렌더링하고 결함만 랜덤화합니다. 이전 버전은 위치/반지름을
몇 픽셀 단위로 랜덤화했는데, 검증 정확도가 거의 우연 수준인 ~60%까지 무너졌습니다: 원본 픽셀 특징에는 이동
불변성(translation invariance)이 없기 때문에, RandomForest가 훨씬 작은 결함 신호 대신 경계 지터 노이즈를
학습해버린 것입니다. 위치/반지름을 먼저 고정하자 정확도가 ~86.7%까지 올라갔습니다. 형태 다양성이나 지터를 다시
추가한다면 특징 표현 방식도 함께 바꿔야 합니다(예: 원본 픽셀 대신 엣지/그래디언트 특징). 그렇지 않으면 정확도가
같은 이유로 다시 저하됩니다.

`generate_data.py`의 `ambiguous_ratio`는 일부러 낮은 심각도의 결함을 가진 NG 이미지를 일정 비율 생성합니다. 이는
review-queue Phase가 수집할 만한 진짜 애매하고 낮은 confidence 케이스가 존재함을 보장합니다 — 이게 없으면 잘
분리된 합성 데이터셋에서는 오분류가 0건이 나와 리뷰할 것이 아무것도 없을 수 있습니다.

OK 이미지에는 추가로 픽셀 단위 가우시안 노이즈(`NOISE_SIGMA`)가 들어가고, `benign_artifact_ratio` 비율만큼은
경미한 NG 결함과 크기가 동일하지만 OK로 라벨링된 흐릿한 얼룩(먼지/반사光 같은 실제 이물질의 대역, 진짜 결함이
아님)이 추가됩니다. 이게 없으면 모든 OK 이미지 렌더링이 바이트 단위로 완전히 동일했기 때문에(위치/반지름/픽셀에
분산이 전혀 없음), model_v1이 모든 OK 이미지에서 100% 확신·100% 정답을 냈습니다 — 그러면 리뷰 큐는 구조적으로
NG로만 채워질 수밖에 없고, PLAN.md의 두 번째 오류 방향("모델이 OK를 NG로 오판")은 애초에 발생할 수 없는 구조였습니다.
이로 인해 val accuracy는 ~75.8%로 낮아졌고, 일부 실제 OK 이미지가 진짜 낮은 confidence 케이스로 리뷰 큐에
들어가게 됐습니다. 현재 튜닝값에서는 val set에서 실제 OK→NG 오분류는 여전히 0건입니다(OK recall은 100% 유지);
benign-artifact 크기를 더 키우면 NG recall(이미 ~52%로 낮음)을 희생하는 대가로 이 값도 바뀔 가능성이 큽니다 —
이 부분을 건드릴 때는 버그가 아니라 튜닝 손잡이로 취급하세요.

### 사람 검토는 폴더 기반·해시 매칭이며, 파일명 매칭이 아님

`data/new/review/{ok,ng}/`는 사람이 화면 없이도 이미지를 직접 눈으로 보고 실제로 분류해 넣는 곳입니다.
`state/`가 아니라 `data/new/`(`images/`와 나란히) 아래에 두어, 검토자가 같은 배치의 이미지를 위해 최상위
디렉터리 두 곳을 오가지 않아도 되게 했습니다. `label_review_queue.py`는 파일명을 절대 신뢰하지 않습니다: 두
폴더를 재귀적으로 순회하며 sha256 콘텐츠 해시로 파일을 `review_queue.json` 항목에 매칭합니다(대기 중인 이미지를
복사해 넣을 때 `prepare_review_inbox.py`가 이 해시를 찍어둡니다). 이는 우연이 아니라 의도된 설계입니다 — 실제
검토자는 파일명을 바꾸거나 실수로 중첩 폴더에 넣기 마련이고, 매칭 로직은 이런 상황에서도 살아남아야 합니다.
또한 큐가 인식하지 못하는 내용의 파일은 조용히 무시되거나 크래시하는 대신 "알 수 없음"으로 보고되며, 같은
이미지가 `ok/`와 `ng/` 양쪽에 있으면 임의로 한쪽을 골라 해결하는 대신 충돌로 보고됩니다. 이 매칭 로직을 건드릴
때는 반드시 해시 기반을 유지하세요 — 파일명 매칭을 다시 들여오면 이 설계가 원래 막으려던 실패 사례가 그대로
재발합니다.
