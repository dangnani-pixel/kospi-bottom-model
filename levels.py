"""추세선·지지·저항선 (오픈소스 trendln 라이브러리로 계산).

trendln(https://github.com/GregoryMorse/trendln, MIT)의
- calc_support_resistance((저가, 고가)): 저점끼리·고점끼리 이은 추세선 후보(지나는 점 수, 기울기, 절편)
- get_horizontal_levels((저가, 고가)): 비슷한 가격의 저점·고점을 묶은 수평 지지·저항 가격대
를 써서, 일봉 최근 250거래일·주봉 최근 156주에 대해 계산한다.
사이트는 결과(json)를 그대로 그린다. 그날까지의 자료만 쓰므로 과거 봉에 미래 값이 섞이지 않는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import trendln

OUT = Path(__file__).resolve().parent
WINDOWS = {"day": 250, "week": 156}


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    key = df.index - pd.to_timedelta(df.index.day_of_week, unit="D")
    g = df.groupby(key)
    w = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})
    w.index = g.apply(lambda x: x.index[-1])  # 그 주 마지막 거래일
    return w


def compute(df: pd.DataFrame, n: int) -> dict:
    d = df.tail(n).dropna()
    if len(d) < 30:
        return {}
    lo, hi, cl = d["low"].to_numpy(float), d["high"].to_numpy(float), d["close"].to_numpy(float)
    dates = [f"{x:%Y-%m-%d}" for x in d.index]
    last, price = len(d) - 1, float(cl[-1])
    res = trendln.calc_support_resistance((lo, hi), window=len(d), errpct=0.005, accuracy=2)
    (_, _, mintrend, _), (_, _, maxtrend, _) = res
    lines = []
    for kind, trend in (("sup", mintrend), ("res", maxtrend)):
        cand = []
        for pts, r in trend:
            if len(pts) < 3:  # 세 점 이상 지나는 선만(두 점은 아무 선이나 그릴 수 있어서)
                continue
            slope, icpt = float(r[0]), float(r[1])
            p0, p1 = int(min(pts)), int(max(pts))
            at_last = slope * last + icpt
            if not np.isfinite(at_last) or at_last <= 0 or last - p0 < 10 or abs(at_last / price - 1) > 0.3:  # 현재가에서 30% 넘게 먼 선은 뺌
                continue
            # trendln 후보 중, 선을 그은 뒤 종가가 선을 1% 넘게 뚫은 봉이 5% 이하인 '지켜진' 선만 쓴다(마지막 봉 제외)
            xs = np.arange(p0, last)
            line = slope * xs + icpt
            viol = (cl[p0:last] < line * 0.99) if kind == "sup" else (cl[p0:last] > line * 1.01)
            if viol.mean() > 0.05:
                continue
            cand.append({"kind": kind, "d1": dates[p0], "v1": round(slope * p0 + icpt, 2), "d2": dates[last],
                         "v2": round(at_last, 2), "touches": len(pts), "last_pt": dates[p1], "p1": p1,
                         "broken": bool(price < at_last * 0.99) if kind == "sup" else bool(price > at_last * 1.01)})
        # 접촉 점이 많고 최근까지 닿은 선 1개
        cand.sort(key=lambda c: (-c["touches"], -c["p1"]))
        for c in cand[:1]:
            c.pop("p1")
            lines.append(c)
    sup, resl = trendln.get_horizontal_levels((lo, hi), pctbound=0.015, min_touches=2)
    hz = [{"kind": "sup", "price": round(float(p), 2), "touches": int(t)} for p, t, _ in sup if p < price][:2]
    hz += [{"kind": "res", "price": round(float(p), 2), "touches": int(t)} for p, t, _ in resl if p > price][:2]
    return {"from": dates[0], "to": dates[-1], "lines": lines, "levels": hz}


def for_frame(df: pd.DataFrame) -> dict:
    return {"day": compute(df, WINDOWS["day"]), "week": compute(weekly(df), WINDOWS["week"])}


def main() -> int:
    d = OUT / "levels"
    d.mkdir(exist_ok=True)
    for name in ["kospi", "kosdaq"]:
        p = OUT / f"{name}_ohlc.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, index_col=0, parse_dates=True)
        out = for_frame(df)
        (d / f"{name}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(name, {k: (len(v.get("lines", [])), len(v.get("levels", []))) for k, v in out.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
