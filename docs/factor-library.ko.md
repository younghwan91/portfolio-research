# 팩터 라이브러리 — 158개

[← README](../README.ko.md) · [English](factor-library.md)


팩터를 158개 함수로 구현하지 않는다. **선언적 표현식(DSL)** 으로 쓰면 TTM·QoQ·YoY·가속 파생형이 자동 생성된다.

```python
from opt_portfolio.factor.dsl.expr import F
from opt_portfolio.factor.dsl.registry import factor

# 현금 기반 영업수익성 (Ball et al. 2016)
CBOP = factor(
    "CBOP",
    (F.gp - _delta(F.receivables) - _delta(F.inventory) + _delta(F.liabilitiesc)) / F.assets,
    category="quality",
    direction=1,
    neutralize=("sector",),   # 섹터 중립화
)
```

| 카테고리 | 개수 | 예 |
|---|---|---|
| quality | 55 | GP_A, ROIC, F-Score, 발생액, 순영업자산 |
| growth | 26 | 매출·이익 YoY/QoQ |
| price | 24 | 모멘텀 1/3/6/12개월, 12-1, 저변동성 |
| value_price | 24 | PER, PBR, PSR, PFCR, PGPR |
| acceleration | 15 | 성장률의 2차 미분 |
| value_ev | 9 | EV/EBITDA, EV/GP |
| flow_proxy | 5 | 13F 기관 보유 변화, 내부자 순매수 |

문헌 근거가 있는 것만 담는다 — Novy-Marx(2013), Sloan(1996), Hirshleifer et al.(2004), Daniel & Titman(2006), Ball et al.(2016), Chen & Zimmermann 오픈소스 라이브러리 복제 등.


정의는 `src/opt_portfolio/factor/library/` 에 있고, 명세는
[`factor-system/01-factor-spec.md`](factor-system/01-factor-spec.md) 다.
