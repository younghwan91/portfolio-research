# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **상수 수익률에서 `calculate_sharpe_ratio` 가 inf 를 돌려줬다.** `returns.std() == 0`
  검사는 부동소수 오차(1e-18)로 통과하고 `excess.std()` 는 정확히 0 이 되어
  mean/0 이 됐다. 매 테스트 실행마다 `RuntimeWarning: divide by zero` 가 남았고,
  기존 테스트 두 개는 그 상수 시계열로 inf > 0 을 "양의 Sharpe" 로 통과시키고
  있었다. 이 함수는 factor/·taa/ 와 공유한다.
- `VAAStrategy(use_forecasting=False)` 가 예측 추천 경로에 들어가면 `None.forecast`
  로 죽을 수 있었다 — None 검사를 넣는다.
- `DataCache.get_missing_date_ranges` / `get_incremental_data` 가 `str` 인자를
  `pd.to_datetime` 결과로 덮어써서 타입이 `str | datetime` 으로 남았다.
- `scripts/update_readme_performance.py` 표 각주의 "보유 종목은 공개하지 않는다 —
  초소형주" 문구. 운용 후보가 대형주 E안으로 바뀌고 파라미터를 전부 공개한
  뒤에도 남아 있어, 재생성하면 사실과 다른 문구가 README 에 되살아날 상태였다.
- CLAUDE.md 의 "구독 종료·ingest 실패" 서술. README 는 08-26 에 정정했는데 이
  파일은 넉 달간 그대로였다. 스토어는 `quant-airflow` 가 계속 재구축한다
  (2026-10-05 실측 `prices` 최신일 2026-09-10).

### Changed

- **mypy 가 트리 전체를 막는다.** 구 VAA·분석·코어 코드의 63건을 전부 해소하고
  CI 의 "legacy — 보고용"(continue-on-error) 단계를 없앴다. `make typecheck` =
  `mypy src/ scripts/` + `mypy run.py`.
- 구 VAA 서브시스템에 단위 테스트 139개 추가 — `strategies/` 커버리지 11~27% →
  98~100%, 전체 58% → 65%. 네트워크 없이 돈다.
- 클래스 범위 pytest 픽스처를 classmethod 로 — pytest 10 에서 제거되는 형태였다.
- CI 매트릭스에 Python 3.13 추가. pre-commit ruff 핀 v0.16.2 → v0.16.9.

### Known issues (미수정, 테스트는 현 동작을 고정)

- `ou_process.py` 두 시뮬레이션의 `range(1, forecast_days)` 는 21일 지평을
  20걸음만 걷고, `future_dates` 는 현재값 열을 첫 미래 영업일로 라벨한다.
- `OUForecaster.calibrate` 의 μ 가 0.999 로 클립된 slope 로 계산되어 추세
  시계열에서 회귀 목표가 비현실적으로 커진다.

## [3.1.0] - 2026-08-16

### Added

- **변동성 타게팅** (`backtest/timing.py`) — 실현변동성에 반비례하는 연속 익스포저
  (Moreira & Muir 2017). 기존 오버레이는 켜짐/꺼짐 이진이라 서서히 오르는
  변동성에 점진적으로 대응하지 못했다.
- **파라미터 앙상블** (`--ensemble k`) — 폴드마다 최적값 하나에 검증 구간
  전체를 걸던 것을, 상위 k개 파라미터의 검증 수익률 평균으로 바꾼다.
  `n_stocks` 가 폴드에 따라 15↔47 로 널뛴 것이 동기다.
- **섹터 비중 상한** (`max_sector_weight`) — 팩터는 섹터 중립화하는데 최종
  포트폴리오의 섹터 비중은 아무도 보지 않았다. 실제 보유 19종목 중 6종목이
  Technology 였다 — 팩터 베팅이 아니라 의도하지 않은 매크로 베팅이다.
- `scripts/update_readme_performance.py` — README 성과 표·그래프를 저장된 OOS
  수익률에서 생성한다. 종목명은 쓰지 않는다.
- `scripts/run_backtests.sh` — 풀 히스토리 walk-forward 순차 실행

### Fixed

- **분기→일별 승격 캐시에 크기 제한이 없었다.** 승격 프레임 하나가 362MB
  (9,000 거래일 × 6,895종목)라 팩터를 늘릴수록 선형으로 쌓였다. 팩터 20개짜리
  조합 탐색이 OOM 으로 두 번 죽은 원인이며, **팩터 수가 곧 메모리 한계**였다.
  LRU 4개로 제한 — 폴드 1 기준 RSS 10.4GB → 5.29GB, 이후 폴드에서 증가 없음.
- `close.pct_change()` 를 평가 호출마다(폴드 19 × 시도 3) 다시 만들던 것을
  evaluator 에서 한 번만 계산 — 파라미터와 무관한 500MB 프레임이었다.
- walk-forward 폴드 로그에 RSS 를 남긴다. 진행률만 있어서 메모리가 자라는
  것인지 원래 높은 것인지 사후에 구분할 수 없었다.

## [3.0.0] - 2026-08

미국 주식 팩터 엔진 추가. 기존 VAA 시스템과 완전히 격리된 서브시스템이며,
공유하는 것은 `config.RISK_FREE_RATE` 하나뿐이다.

### Added

- **팩터 엔진** (`src/opt_portfolio/factor/`) — 횡단면 팩터 전략 파이프라인
  - PIT 스토어 (DuckDB bitemporal) · 벤더 중립 `Provider` 프로토콜
  - 선언적 팩터 DSL — 158개 팩터, TTM/QoQ/YoY/가속 파생형 자동 생성
  - 유니버스 필터 (유동성·절대 시총 밴드·섹터·재무 건전성)
  - 비중 스킴 7종 — 균등·시총·역변동성·리스크패리티·HRP·MVO·Black-Litterman
  - walk-forward PO (확장/롤링 윈도 · 엠바고) + grid/random/GP-EI 탐색
  - **Deflated Sharpe · PBO** 로 과최적화 정산
  - 마켓타이밍 오버레이 (이평 + 재진입 히스테리시스)
  - 매매 유예구간(`hold_multiple`) · Calmar 목적함수 · 레짐 분류
  - 학습 구간 내 팩터 선택 (`research/selection.py`)
- **운용 도구** — `opt-factor holdings` (오늘 살 종목 · 매매 계획),
  `opt-factor-tui` (운용 화면)
- **팩터 연구소** (`scripts/factor_lab.py`) — 10분할 · IC · 회전율 일괄 평가
- 문서 `docs/factor-system/` 7종 — 설계·PIT 규약·벤더 실측·실험 기록
- 영문 README (기본) + 한국어 README.ko.md

### Changed

- Sharpe 를 프로젝트 전체에서 **초과수익 기준**으로 통일 (`config.RISK_FREE_RATE`)
- 웹 GUI 제거 — 터미널 UI 만 유지

### Fixed

- **DSR 단위 오류** — 연율화 Sharpe 분산을 기간 단위 자리에 넘겨 DSR 이
  성과와 무관하게 0 에 붙었다. 같은 수익률에서 0.000 vs 0.910.
- **메모리** — 팩터 패널을 일별로 캐시하던 것을 신호일 그리드로 (21배 절감),
  일별 필드를 SQL 단계에서 선택 (OOM 3회의 원인)
- 벤더 함정 — 요청당 티커 30개 상한, DAILY 백만 달러 단위, TICKERS 10,000행
  절단, `isdelisted` 미정규화, PIT 위반 행, ticker 결측 행
- 벤치마크(SPY)가 유니버스 필터에 잘려 마켓타이밍이 죽던 문제

### Removed

- `data_cache.py` (루트) — `core/cache.py` 와 중복이며 참조되지 않았다
- `requirements.txt` — CI·Makefile 어디서도 쓰이지 않으면서 dependabot 만
  물고 있었다 (제거한 streamlit 의 버전 상향 PR 이 계속 올라온 원인).
  의존성 원천은 `pyproject.toml` + `uv.lock` 하나다.

## [2.0.0] - 2025

### Added
- Dynamic VAA backtest engine with monthly walk-forward simulation
- Sharpe Ratio grid-search optimizer (VAA: 20–70%, core: 5–35%)
- Ornstein-Uhlenbeck process forecasting for momentum prediction
- Streamlit Web UI with interactive Plotly charts
- CLI interface with Korean language support
- DuckDB-backed incremental cache (only fetches missing date ranges)
- Risk analytics: Sharpe, Sortino, VaR/CVaR, max drawdown, calmar ratio
- Performance attribution and rolling return analysis
- `AllocationConfig.from_weights()` for dynamic weight customization
- `run.py` interactive menu with 9 options

### Changed
- Full modularization into `core/`, `strategies/`, `analysis/`, `ui/`, `utils/`
- UI translated to Korean
- `CORE_WEIGHT` replaced with individual asset weights (`SPY_WEIGHT`, `TLT_WEIGHT`, `GLD_WEIGHT`, `BIL_WEIGHT`)

## [1.0.0] - 2024

### Added
- Initial VAA (Vigilant Asset Allocation) strategy implementation
- Keller's momentum formula: `12×(1M) + 4×(3M) + 2×(6M) + 1×(12M)`
- Aggressive universe: SPY, EFA, EEM, AGG
- Protective universe: LQD, IEF, SHY
- Core positions: SPY, TLT, GLD, BIL
- Yahoo Finance data fetching via `yfinance`
- MIT License

[Unreleased]: https://github.com/yourusername/opt_portfolio/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/yourusername/opt_portfolio/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/yourusername/opt_portfolio/releases/tag/v1.0.0
