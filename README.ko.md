# portfolio-research

**한국어** · [English](README.md)

**미국 주식 팩터 투자 엔진 + ETF 전술적 자산배분(TAA) 검증 시스템.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-younghwan--chae-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/younghwan-chae/)

세 개의 서브시스템이 한 저장소에 있다.

| | **팩터 엔진** (`factor/`) | **TAA 자산배분** (`taa/`) | **VAA 원본** (`strategies/`) |
|---|---|---|---|
| 대상 | 미국 개별주 (20,931종목, 1997~2026) | ETF 18종 | ETF 7~11종 |
| 질문 | 어떤 종목을 살까 | 어떤 자산군으로 갈아탈까 | (같음 — 첫 시도) |
| 데이터 | Sharadar 직판 (PIT · 상장폐지 포함) | Sharadar 펀드 벌크 (`closeadj`) | yfinance 일간 종가 |
| 진입점 | `opt-factor` · `opt-factor-tui` | `scripts/run_taa.py` | `make run` · `run.py` |
| 결과 | **채택 1건** (대형주 E안) | **채택 0건** — 9개 전부 PBO 관문 탈락 | 보존 — 왜 실패했는지의 기록 |

**세 시스템은 서로를 import 하지 않는다.** 예외는 `taa/` →
`factor.research.overfitting`(DSR·PBO) 하나뿐이다. 관문 없이 만든 성과를 믿지 않는
것이 이 저장소의 규약이기 때문이다.

---

# 1. 팩터 엔진

미국 주식 횡단면 팩터 전략을 **검증 가능한 방식으로** 만드는 엔진이다.
핵심 설계 원칙은 하나다 — **조용히 틀리지 않는다.**

## 왜 이 엔진인가

퀀트 백테스트가 실패하는 방식은 대개 정해져 있고, 이 엔진은 그 각각을 구조로 막는다.

| 흔한 실패 | 이 엔진의 대응 |
|---|---|
| 생존편향 — 지금 살아남은 종목만 본다 | 상장폐지 종목 포함 (엔론·구 아메리칸항공 등 실제 확인) |
| Look-ahead — 발표 전 숫자를 쓴다 | 표현식이 원시 테이블에 접근 못 하고 `PanelContext` 만 통과, `datekey` 정렬 강제 |
| 재공시 오염 — 정정된 숫자를 쓴다 | **최초 공시 우선** — 시장이 처음 본 값만 저장 |
| 조용한 절단 — 데이터가 덜 왔는데 성공 처리 | 페이지네이션이 기대 범위 미달 시 `TruncatedDataError` |
| 과최적화 — 수백 번 돌려 최고를 고른다 | **DSR**(Deflated Sharpe) + **PBO** 로 시도 횟수를 정산 |
| 인샘플 성과 보고 | 공식 성과는 **walk-forward** 뿐. 단일 백테스트는 참고용 명시 |

## 성과

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/performance-dark.png">
  <img alt="대형주 5팩터 + 200일 타이밍의 walk-forward 검증 구간 누적 성장 — 2002-12부터 2026-08까지 15bps 36배, 50bps 27배, SPY 14배. 세로축 로그" src="docs/images/performance-light.png">
</picture>

*세로축은 로그다 — 기울기가 같으면 수익률이 같다. 2008·2012·2022 의 평평한
구간은 200일 이평이 현금으로 뺀 자리다. 그 세 번이 SPY 와 낙폭이 갈리는 지점이다.*

<!-- PERFORMANCE:START -->

*운용 후보 · walk-forward 검증 구간 · 2002-12 – 2026-08 (23.6년)*

**대형주 5팩터 + 200일 이평 타이밍** (`configs/strategy_lean_timed.json`)

| 지표 | 슬리피지 15bps | 슬리피지 50bps | SPY (같은 구간) |
|---|---|---|---|
| 연평균 수익률 | **16.34%** | 14.91% | 11.66% |
| 최대낙폭 | −24.3% | −24.3% | −55.2% |
| 변동성 | 15.7% | 15.7% | 18.6% |
| Sharpe | **0.727** | 0.648 | 0.418 |
| Calmar | **0.67** | 0.61 | 0.21 |
| Deflated Sharpe (파라미터 시도 72회) | **0.996** ✓ | 0.988 ✓ | — |
| Deflated Sharpe (**전략 탐색 35회**) | **0.982** ✓ | 0.957 ✓ | — |
| PBO (35개 구성 CSCV · 월별 · S=16) | **0.303** ✓ | — | — |

**이 전략은 방어 장치를 켠 채로 측정됐다** — 최소 주가 $5 · 최소 거래대금 $1M ·
슬리피지. 유니버스가 역대 S&P500 이라 **용량 제약이 없다.** 슬리피지를 50bps 로
올려도 낙폭과 변동성이 그대로고 수익만 1.4%p 깎인다.

마지막 두 줄은 **walk-forward 바깥**을 정산한 값이다 — "35개 전략을 훑어 하나를
골랐다"는 상위 탐색까지 시도 횟수에 넣었다. 관문 설정(월별 · S=16)을 고른 근거는
아래에 있다. 재현: `uv run python scripts/strategy_search_cost.py` — 벤더 데이터
없이 `results/oos/` 만으로 돈다.

<!-- PERFORMANCE:END -->

## 폐기한 것과 그 대가

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/guards-dark.png">
  <img alt="초소형주 전략의 누적 성장 — 방어 장치를 끄면 153배, 켜면 0.040배로 원금의 96%를 잃는다. 세로축 로그" src="docs/images/guards-light.png">
</picture>

*같은 전략, 같은 구간. 차이는 슬리피지·최소 주가·최소 거래대금뿐이다. 파란 선이
2026-08-16 까지 이 README 의 표제였다.*

CAGR 23.78% 의 **초소형주 8팩터 전략**이 이 자리에 있었다. 설계 문서가 필수라고
적은 방어 장치 셋을 켜자 무너졌다 — **Sharpe 1.047 → −0.224.** 방어를 켜면
유니버스의 98% 가 사라지기 때문이다. 표제는 대형주 전략으로 옮겼다. 그쪽은 처음부터
방어를 켠 채로 쟀고, 그래서 두 전략을 같은 조건에서 비교한 적이 없었다.

DSR 관문에서 기각한 후보가 스무 개를 넘고, PBO 는 제대로 재기 전까지 두 번 틀린 채로
발표됐고, 자산배분 9개 구성은 사전등록한 뒤 전부 기각했다. **그 자취를 전부 남겼다 —**
[`docs/journal/`](docs/journal/README.ko.md).

## 팩터 라이브러리 — 158개

158개의 함수를 쓴 것이 아니다. **선언형 표현식 DSL** 이 TTM·QoQ·YoY·가속 변형을
자동 생성하고, 문헌 근거가 있는 것만 담는다(Novy-Marx 2013, Sloan 1996,
Ball et al. 2016, Chen & Zimmermann 오픈소스 라이브러리 복제 등).
분류와 개수는 [`docs/factor-library.ko.md`](docs/factor-library.ko.md).

## 사용법

> **여기 실린 모든 숫자는 2026-08-14 까지의 데이터로 측정했고**,
> [`results/`](results/) 의 산출물이 그대로 담겨 있다 — 그래서 보고된 성과는
> **벤더 데이터 없이도 확인할 수 있다.** 다시 돌리려면
> [Sharadar](https://sharadar.com) 구독이 필요하다. PIT 재무제표와 폐지 종목
> 커버리지를 함께 주는 유일한 소매 가격 소스다. 어댑터는 중립적인 `Provider`
> 프로토콜 뒤에 격리돼 있어 소스 교체는 파일 하나를 다시 쓰는 일이다.

```bash
# 데이터 적재 (Sharadar 구독 필요)
export SHARADAR_API_KEY=...
opt-factor ingest --store us.duckdb --provider sharadar \
  --tables sf1,sep,daily,actions,sp500,tickers

# 팩터 예측력 검증 — 10분할 · IC · 회전율
uv run python scripts/factor_lab.py --store us.duckdb --factors GP_A,PER,SIZE

# 공식 성과 (walk-forward + DSR)
opt-factor optimize --store us.duckdb --config configs/strategy_lean_timed.json \
  --space configs/space.json --objective calmar

# 오늘 살 종목 (현재 보유를 주면 매매 계획까지)
opt-factor holdings --store us.duckdb \
  --config configs/strategy_lean_timed.json --current my_holdings.csv
```

전략은 [`configs/`](configs/README.md) 의 JSON 한 파일로 완전히 선언된다 — 채택된
것도, 기각된 것도, 폐기한 것도, 운용 후보의 파라미터까지 전부 공개한다.

---

# 2. 전술적 자산배분 (TAA)

개별 종목 대신 ETF 18종을 매월 교체한다. **9개 구성을 사전등록했고 9개 전부
기각했다 — PBO 0.770.** 관문을 완화하지 않았다.

아무것도 안 통한다는 뜻은 아니다. BAA(Keller 2022) 변형 6개는 예외 없이 Calmar 에서
60/40 을 이긴다(0.535~0.812 대 0.354). 다만 그 6개만으로 잰 PBO 가 0.861 이라
**그중 어느 것이 최선인지는 이 데이터로 정할 수 없다.** 두 문장은 함께 서야 한다.

9개 구성과 이 과정에서 잡은 결함 8건, VAA 가 논문의 16~17% 대신 여기서 6.07% 로
측정된 이유는 [`docs/taa/01-results.md`](docs/taa/01-results.md) 와
[`docs/journal/`](docs/journal/README.ko.md) 에 있다.

```bash
uv run python scripts/run_taa.py    # 9개 구성 · PBO · 판정표
make run                            # VAA 원본 (yfinance, 보존용)
```

---

## 설치 & 개발

```bash
make install        # uv sync --extra dev
make test           # pytest + coverage (403 tests)
make lint           # ruff check + format --check
make typecheck      # mypy src/
```

패키지 관리는 **uv**(`uv.lock`)다. `pip install` 하지 않는다. 코드는
`src/opt_portfolio/` 아래 `factor/`·`taa/`·`strategies/` 로 나뉘고 `analysis/`·`core/`
를 공유한다.

설계 문서는 [`docs/factor-system/`](docs/factor-system/) 에 있다 — 명세,
**데이터 계약**(스토어 스키마 · PIT 규약 · 벤더 실측), walk-forward 수식, 그리고
기각 목록이 담긴 **실험 로그**. 영어 요약은
[`docs/journal/`](docs/journal/README.md) 와
[`docs/factor-library.md`](docs/factor-library.md).

## 한계와 가정

- **구간에 큰 낙폭이 세 번밖에 없다**(2008·2020·2022). 낙폭 방어를 주장하는 전략이
  그 주장을 사건 세 개에 걸고 있다. 남은 한계 중 가장 크다.
- **거래비용은 측정이 아니라 가정이다.** 15bps 와 50bps 를 모두 보고하고 결론은
  양쪽에서 유지되지만, 실제 보유 종목의 실현 스프레드는 잰 적이 없다.
- **팩터 집합 자체는 정산되지 않았다.** 124개를 훑어 5개를 골랐고, 그 탐색에는 아직
  시도 횟수가 매겨지지 않았다. 전략 35개의 외부 탐색은 정산했다(PBO 0.303 · DSR 0.982).
- **숫자는 2026-08-14 에서 멈춰 있다.** 이후 벌크로 다시 잰 것은 없다. Sharadar 구독을
  종료해 `ingest` 는 이제 실패하며, 그건 버그가 아니다. 세금은 반영하지 않았다.
- TAA 는 채택이 0건이라 운용 결론이 없다. `strategies/` 의 VAA 원본은 다른 데이터
  소스에서 in-sample 로 최적화한 것이다 — 비교하려면 `taa/` 숫자를 쓴다.

> ⚠️ 모든 백테스트는 과거 데이터 기반이며 미래 수익을 보장하지 않는다.

## 라이선스

MIT

---
## ⭐ 도움이 되셨다면

이 프로젝트가 유용했다면 우측 상단 **[⭐ Star](https://github.com/younghwan91/portfolio-research)** 를 눌러주세요. 검색·추천 노출이 올라가 더 많은 분들이 찾을 수 있습니다.

- 🐛 버그·질문 → [Issues](https://github.com/younghwan91/portfolio-research/issues)
- 📈 업데이트 소식 → [팔로우 @younghwan91](https://github.com/younghwan91)

## 관련 프로젝트 — 오픈소스 퀀트 스택

한국·미국 주식과 암호화폐를 아우르는 오픈소스 스택입니다. 각 저장소는 독립적으로 쓸 수 있습니다.

| 축 | 프로젝트 | 설명 |
|---|---|---|
| 🇰🇷 한국 주식 | **[kiwoom-client](https://github.com/younghwan91/kiwoom-client)** | 키움증권 REST API Python 라이브러리 — 국내주식 엔드포인트 전수·실시간 WebSocket, sync + async (`pip install kiwoom-client`) |
| 🇰🇷 한국 주식 | **[krx-fundamentals-client](https://github.com/younghwan91/krx-fundamentals-client)** | 국내 기업 펀더멘탈 Python 클라이언트 라이브러리 — 재무제표·투자지표·배당·종목 스크리닝 (DART + KRX + 네이버) |
| 🇰🇷 한국 주식 | **[krx-news-client](https://github.com/younghwan91/krx-news-client)** | 한국 주식 뉴스·공시 수집 Python 클라이언트 라이브러리 (DART + 한국경제 + 더벨 + 토스) |
| 🇰🇷 한국 주식 | **[fin-checkup](https://github.com/younghwan91/fin-checkup)** | 관심종목 위험 공시 텔레그램 알림 + DART·SEC 재무 건강검진 — 측정값과 사실만 전달한다 |
| 🇰🇷 한국 주식 | **[quant-airflow](https://github.com/younghwan91/quant-airflow)** | 시세·수급·실적을 TimescaleDB 로 수집하는 Airflow 파이프라인 — 상장폐지 종목까지 담아 생존편향을 막는다 |
| 🇰🇷 한국 주식 | **[kr-quant](https://github.com/younghwan91/kr-quant)** | 코스피·코스닥 알파 리서치 — walk-forward·랜덤 음성대조·purged CV·Deflated Sharpe 를 CI 가드레일로 강제 |
| 🇺🇸 미국 주식 | **[automated-stock-trading-systems](https://github.com/younghwan91/automated-stock-trading-systems)** | Bensdorp 의 7개 비상관 트레이딩 시스템 백테스터 (교육용 재구현) |
| ₿ 암호화폐 | **[quantbox-engine](https://github.com/younghwan91/quantbox-engine)** | 암호화폐 선물 백테스트·실행 엔진 — 룩어헤드 0, 백테스트↔실거래 일체화 |

## 만든 사람

**채영환 (Younghwan Chae)** · [GitHub @younghwan91](https://github.com/younghwan91) · [LinkedIn](https://www.linkedin.com/in/younghwan-chae/)

전체 오픈소스 퀀트 스택은 [프로필](https://github.com/younghwan91)에서 한눈에 볼 수 있습니다.
