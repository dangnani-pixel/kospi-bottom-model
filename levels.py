"""추세선·지지·저항선 (오픈소스 라이브러리로 계산: trendln, pytrendline, pricelevels).

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

try:
    import trendln
except Exception as e:  # noqa: BLE001
    trendln = None
    print("trendln 없음:", e)
try:
    if not hasattr(pd.DataFrame, "append"):  # pytrendline은 예전 pandas의 DataFrame.append를 씀(pandas 2에서 삭제됨)
        def _append(self, other, ignore_index=False, **kw):
            if isinstance(other, dict):
                other = pd.DataFrame([other])
            elif isinstance(other, pd.Series):
                other = other.to_frame().T
            return pd.concat([self, other], ignore_index=ignore_index)
        pd.DataFrame.append = _append
    import pytrendline
except Exception as e:  # noqa: BLE001
    pytrendline = None
    print("pytrendline 없음:", e)
try:
    from pricelevels.cluster import ZigZagClusterLevels
except Exception as e:  # noqa: BLE001
    ZigZagClusterLevels = None
    print("pricelevels 없음:", e)

OUT = Path(__file__).resolve().parent
WINDOWS = {"day": 250, "week": 156}


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    key = df.index - pd.to_timedelta(df.index.day_of_week, unit="D")
    g = df.groupby(key)
    w = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})
    w.index = g.apply(lambda x: x.index[-1])  # 그 주 마지막 거래일
    return w


def _trendln(d: pd.DataFrame, dates: list[str]) -> dict:
    lo, hi, cl = d["low"].to_numpy(float), d["high"].to_numpy(float), d["close"].to_numpy(float)
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
    return {"lines": lines, "levels": hz}


def _pytrendline(d: pd.DataFrame, dates: list[str], interval: str) -> dict:
    """pytrendline.detect: 3점 이상 지나고 돌파되지 않은 추세선 중 점수(score)가 가장 높은 지지·저항 1개씩."""
    x = d.rename(columns=str.capitalize).reset_index(drop=True)
    x["Date"] = pd.to_datetime(dates)
    cd = pytrendline.CandlestickData(df=x, time_interval=interval, open_col="Open", high_col="High", low_col="Low",
                                     close_col="Close", datetime_col="Date")
    r = pytrendline.detect(candlestick_data=cd, trend_type=pytrendline.TrendlineTypes.BOTH, min_points_required=3,
                           scan_from_date=None, ignore_breakouts=True)
    last, price = len(d) - 1, float(d["close"].iloc[-1])
    lines = []
    for kind, key in (("sup", "support_trendlines"), ("res", "resistance_trendlines")):
        t = r.get(key)
        if t is None or not len(t):
            continue
        t = t[t["is_best_from_duplicate_group"] == True]  # noqa: E712
        t = t.assign(at_last=t["m"].astype(float) * last + t["b"].astype(float))
        t = t[(t["at_last"] - price).abs() <= price * 0.3]
        if not len(t):
            continue
        b = t.sort_values("score", ascending=False).iloc[0]
        i0, m, c = int(b["starts_at_index"]), float(b["m"]), float(b["b"])
        lines.append({"kind": kind, "d1": dates[i0], "v1": round(m * i0 + c, 2), "d2": dates[last], "v2": round(m * last + c, 2),
                      "touches": int(b["num_points"]),
                      "broken": bool(price < m * last + c) if kind == "sup" else bool(price > m * last + c)})
    return {"lines": lines}


def _pricelevels(d: pd.DataFrame) -> dict:
    """pricelevels ZigZagClusterLevels: ZigZag로 고점·저점을 찾고 1.5% 안에서 군집으로 묶은 가격대(2번 이상), 현재가에서 가까운 2개씩."""
    zl = ZigZagClusterLevels(peak_percent_delta=0.05, merge_distance=None, merge_percent=1.5, min_bars_between_peaks=5, peaks="All")
    zl.fit(d.rename(columns=str.capitalize))
    price = float(d["close"].iloc[-1])
    lv = [g for g in (zl.levels or []) if g["peak_count"] >= 2]
    sup = sorted([g for g in lv if g["price"] < price], key=lambda g: -g["price"])[:2]
    res = sorted([g for g in lv if g["price"] >= price], key=lambda g: g["price"])[:2]
    return {"levels": [{"kind": k, "price": round(float(g["price"]), 2), "touches": int(g["peak_count"])}
                       for k, arr in (("sup", sup), ("res", res)) for g in arr]}


def compute(df: pd.DataFrame, n: int, interval: str = "1d", heavy: bool = True) -> dict:
    d = df.tail(n).dropna()
    if len(d) < 30:
        return {}
    dates = [f"{x:%Y-%m-%d}" for x in d.index]
    out = {"from": dates[0], "to": dates[-1]}
    for name, fn in (("trendln", lambda: _trendln(d, dates) if trendln else None),
                     ("pytrendline", lambda: _pytrendline(d, dates, interval) if (pytrendline and heavy) else None),
                     ("pricelevels", lambda: _pricelevels(d) if ZigZagClusterLevels else None)):
        try:
            r = fn()
            if r is not None:
                out[name] = r
        except Exception as e:  # noqa: BLE001
            print(f"  {name} 실패:", e)
    return out


def for_frame(df: pd.DataFrame, heavy: bool = True) -> dict:
    """heavy=False면 계산이 오래 걸리는 pytrendline(한 번에 수 초)을 건너뜀(신고가 종목 수십 개용)."""
    return {"day": compute(df, WINDOWS["day"], "1d", heavy), "week": compute(weekly(df), WINDOWS["week"], "1d", heavy)}


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
        print(name, {tf: {k: v for k, v in o.items() if k not in ("from", "to")} and sorted(k for k in o if k not in ("from", "to")) for tf, o in out.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
