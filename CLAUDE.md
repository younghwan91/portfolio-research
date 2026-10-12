# portfolio-research — 작업 규약

(옛 이름 `opt_portfolio`. 패키지·임포트 경로는 여전히 `opt_portfolio`.) **PUBLIC 저장소다.**

미국 주식 팩터 엔진 + 기존 ETF 자산배분 시스템. **서브시스템은 격리되어 있다.**
- 신규 팩터 코드는 `src/opt_portfolio/factor/` 이하에만 쓴다. 기존 `strategies/`(VAA·OU)·`analysis/`·`core/` 는
  보존 대상이다. 공유하는 것은 `analysis/metrics.py`·`analysis/risk.py`·`utils/visualization.py` 뿐이다.
- 세 번째 `taa/`(ETF 전술적 배분, 2026-08-17)는 격리 규칙의 **유일한 예외** — `factor.research.overfitting`
  (DSR·PBO)을 import 한다. 다른 방향의 import 는 금지. 결과는 `docs/taa/01-results.md`(사전등록 9개, 채택 0개).

## 명령

```bash
make install     # uv sync --extra dev — 패키지 관리는 uv(uv.lock). pip install 하지 않는다
make test        # pytest + coverage (~20초, 540 passed · 3 skipped)
make test-one T=tests/factor/test_dsl.py::TestX::test_y
make lint        # ruff check + ruff format --check (src/ tests/ scripts/)
make format      # ruff --fix + format
make typecheck   # mypy src/ scripts/ + run.py — 트리 전체, 예외 없음 (CI 가 실패로 막는다)
uvx pre-commit run --all-files   # CI 의 pre-commit 잡과 같다 — 푸시 전에 돌린다
```

팩터 엔진 CLI: `opt-factor {factors,status,ingest,validate,backtest,holdings,report,pbo,optimize}`.
사용법은 `uv run opt-factor --help` 와 `docs/factor-system/04-data-contract.md` §5.
**공식 성과 측정은 `optimize`(walk-forward)** 다. `backtest` 는 참고용.

## 절대 규칙

코드·문서 주석이 `CLAUDE.md §N` 으로 이 번호를 가리킨다 — 번호를 바꾸지 않는다.
여기는 요약이고, 사례·수치를 담은 전문은 `docs/rules.md`.

1. **조용한 절단 금지 — 이 프로젝트의 지배적 실패 유형.** 실데이터 버그는 전부 "성공" 로그와 함께 났다.
   요청한 것보다 적게 받으면 예외를 던지거나 최소한 경고를 남긴다. 페이지네이션 종료는 "빈 응답" 이 아니라
   **기대 범위 도달**로 검사하고, 필터·조인·병합 후 행 수가 줄면 로그로 남기고, `limit`(Sharadar 10,000)에
   닿은 응답은 절단 의심으로 다룬다.
   - **1-b. 낙관적인 방향의 어긋남은 스스로 드러나지 않는다.** 설정에서 방어 장치(슬리피지·최소 거래대금·
     최소 주가)를 0/None 으로 끄면 그 이유를 설정 파일이나 커밋에 남긴다. 2026-08-15 에 셋 다 0 인 채로
     27개 실험이 돌았다.
   - **개인 수수료 할인·면제는 비용 가정에 넣지 않는다 — 정가 기준**
     (`CostModel.commission_bps` 기본 5). 할인은 언제든 끝날 수 있어, 무수수료라야 성립하는 전략은 할인이
     끝나면 죽는다(사용자 결정). 비용 가정 완화를 제안하지 않는다.
2. **적재 후에는 반드시 수치로 확인한다.** `status` 만으로는 절단을 못 잡는다. 판정은 기대값 숫자 대조가
   아니라 **벌크 원본 대조**다 — 스토어가 벌크보다 적으면 우리 잘못, 벌크 자체가 줄었으면 벤더 변경.
   `mcap` 결측 0 은 잘못된 기준이다(보통주 약 6%가 정상). 기대값 표·검증 명령은 `docs/rules.md` §2,
   검증 SQL 은 `04-data-contract.md` §5.
3. **PIT 불변식을 깨지 않는다.** `datekey >= reportperiod`(`calendardate` 가 아니다 — 비표준 결산월은
   `datekey < calendardate` 가 정상). `validate_pit_frame()`(`factor/data/provider.py`)이 마지막 방어선.
   최초 공시 우선(정정 무시) · 혼합 소스는 늦은 쪽 공시일(`Panel.avail` element-wise max) · 추정치 소급 금지.
   상세 `04-data-contract.md` §2.
4. **벤더 데이터 함정 — 추측해서 코드를 쓰지 않는다.** Sharadar 직판은 숫자를 문자열로 준다(`to_numeric`).
   DAILY 의 `marketcap`/`ev` 는 **백만 달러**(SF1 은 달러). `assetsavg`·`equityavg`·`invcapavg` 는 ARQ 에서
   전부 null → `avg_balance()`. 절단 방향이 ticker 필터 유무로 뒤집힌다 → 항상 티커 청크로 요청.
   불확실하면 실계정으로 확인하고 `04-data-contract.md` 에 실측을 남긴다(초판의 추정이 버그 4건을 낳았다).
5. **완료 선언 전 증거를 제시한다.** 실제 실행 출력(행 수·날짜 범위·테스트 결과)을 확인한 뒤에 완료라고 말한다.
6. **무거운 실행은 메모리 상한 안에서.** `opt-factor optimize` 는 RSS 5~12GB. 옛 15GB 머신에서 스왑 스래싱으로
   sshd 까지 죽었다(2026-08-22). 지금 머신(simnode)은 RAM 61GB 이지만 다른 레포의 장시간 작업과 공유하고
   **`runbig` 이 없다.** 상한은 `systemd-run --user --scope -p MemoryMax=24G -p MemorySwapMax=0 -- <cmd>`
   (2026-10-05 사용 — user 매니저가 안 떠 있으면 "Failed to connect to user scope bus" 로 실패한다. 그땐
   `free -g` 로 여유를 보고 단독 실행). **walk-forward 는 병렬로 돌리지 않는다** — `scripts/run_backtests.sh` 로 순차.

## 데이터 환경 (2026-10-12 확인)

- **스토어 `~/data/us_micro.duckdb` 는 2026-09-10 에서 멈췄다.** Sharadar 구독을 2026-09-14 해지했고
  quant-airflow 의 `daily_sharadar` DAG 가 꺼졌다(quant-airflow 86885b8). `opt-factor ingest` 로 새 데이터가
  온다고 가정하지 않는다. 게시 수치(README·`07-experiment-log` §5.8)는 2026-08-14 데이터로 쟀고 재측정 안 했다.
- **그 파일은 uid 50000(airflow) 소유 644 라 이 계정이 쓸 수 없고, `PITStore` 는 쓰기 모드로 연다** →
  `opt-factor status --store ~/data/us_micro.duckdb` 도 Permission denied. 복사본
  `~/data/us_micro.local.duckdb` 를 쓴다(SPY 적재됨). 복사본을 새로 만들면 SPY 가 없으니
  `uv run python scripts/ensure_benchmark.py --store <복사본> --funds-zip ~/data/sharadar/raw/funds.csv.zip`
  (확인만은 `--check-only`). `scripts/run_backtests.sh` 는 기본 `STORE` 가 원본이라 `STORE=` 를 넘긴다.
- 벌크 원본 `~/data/sharadar/raw/*.zip` 과 스토어는 커밋하지 않는다(벤더 라이선스, `.gitignore`). 우리가 계산한
  산출물(수익률 시계열·IC 표)은 `results/` 에 공개한다. 매수 목록(holdings CSV)을 공개 레포에 올릴지는
  미결정 — 2026-10-05 엔 `~/data/results/` 에만 두었다. 올리기 전에 묻는다.
- 운용 후보는 **E안** `configs/strategy_lean_timed.json`(5팩터 + 200일 타이밍. '대형주'로 불렸지만 시총 하한이
  없어 2026-10-05 보유 30종목의 시총 중앙값은 $1.8B, 섹터 상한도 없다). 초소형 G안은 방어 장치를
  켜면 무너진다. 수치·남은 제약(팩터 선택이 DSR 시도 수에 미정산 등)은 `docs/rules.md` '알려진 제약'.

## 코드·커밋 규약

- Python 3.10+(CI 3.10~3.13), line-length **100**, ruff(lint+format, isort 는 `I`).
  mypy `disallow_untyped_defs` — 신규 함수에는 타입 힌트 필수(CI 가 트리 전체를 막는다, fcb526d).
- 테스트는 `tests/`(기존) / `tests/factor/`(팩터 엔진). 테스트는 네트워크 없이 돈다.
- **pre-commit 의 `ruff-format` 은 마크다운 안 python 코드 블록도 고친다** — 문서만 고쳐도 `uvx pre-commit run
  --all-files` 를 돌린다(474ee78: 이걸로 푸시가 막혔다). 전역 git 훅이 커밋 때 `uvx pre-commit` 을, 푸시 때
  CI 를 로컬에서 돌린다. `.pre-commit-config.yaml` 을 고친 채 unstaged 로 두면 커밋이 거부된다.
- 커밋 메시지는 **한국어** Conventional Commits(`feat(factor): ...`, `fix(taa): ...`, `docs(claude): ...`).
  본문에는 무엇을 고쳤는지가 아니라 **왜 그게 문제였는지**를 쓴다. 커밋 신원은 레포 git 설정 그대로 —
  `git -c user.email=...` 로 덮지 않는다(`commit-identity.yml` 이 거부).
- 구 VAA 의 알려진 결함 둘(OU `range(1, forecast_days)`·클립된 μ)은 테스트가 현 동작을 고정한다 —
  고치면 구 VAA 동작이 바뀌므로 먼저 묻는다(`CHANGELOG.md` Known issues).
- 구현이 문서와 어긋나면 문서를 고치거나 구현을 고친다. 방치하지 않는다. 이 파일과 README 가 4개월
  어긋났던 일이 있다(56a5fd8) — 데이터·구독 상태를 고칠 땐 README·README.ko·`docs/rules.md` 도 함께 본다.

## 문서 — 해당 작업 전에 읽는다

`docs/factor-system/` 이 설계의 단일 진실 공급원이다.

| 파일 | 내용 |
|---|---|
| `00-overview.md` | 설계 개요, 데이터 소스 선정 근거 |
| `01-factor-spec.md` · `docs/factor-library.md` | 팩터 정의 · 카탈로그 |
| `02-universe-spec.md` | 유니버스 필터 |
| `04-data-contract.md` | **스토어 스키마 · PIT 규약 · 벤더 실측 · 운영 절차** |
| `05-math-spec.md` | 가중·백테스트·walk-forward 수식 |
| `06-provider-review.md` | 벤더 12종 비교 |
| `07-experiment-log.md` | 실험 기록(§5.5 초소형 붕괴 · §5.7 v2 미완 · §5.8 E안) |
| `docs/rules.md` | 절대 규칙·알려진 제약 전문(G안 붕괴·E안 운용 후보·남은 제약) |
| `docs/journal/README.md` | 연구 저널 — 고친 것·폐기한 것·기각한 것 |
| `docs/taa/01-results.md` · `configs/README.md` | TAA 결과 · 설정 공개 방침 |
