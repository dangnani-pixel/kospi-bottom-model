"""코스피 바닥 판정 개선안(v2)과 매크로 참고 지표.

기존 판정(v1)은 그대로 두고 나란히 계산해 비교하기 위한 모듈이다.

v1과 달라진 점
- 후행 지표(126일선)를 빼고, 더 빨리 반응하는 '저점 상승'과 '시장 폭(상승 종목 비율)'을 넣었다.
- '투매 후 진정'을 따로 본다: 최근 60거래일 안에 급락·변동성·하락 종목 비율 중 하나가 극단이었고, 지금은 변동성이 가라앉았는지.
- 외국인 순매수 전환을 수급 항목으로 넣었다.
- 서로 상관이 높은 신용 스프레드·환율·VIX는 '글로벌 위험 완화' 한 묶음(3개 중 2개)으로 셌다.
- 기준값은 고정 숫자 대신 과거 약 5년 분포(백분위)를 쓴다. 백분위는 그날까지의 과거 값만으로 계산한다.
- 판정은 점수(0~7)로 단계를 나눈다.

임계값(60일, 5년, 백분위 수준, 점수 구간)은 결과를 보기 전에 정한 초기값이다. 결과에 맞춰 조정하면 과적합이 된다.
참고용 분석이며 투자 자문이 아니다.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
WIN5Y = 1250          # 약 5년(거래일)
MIN_HIST = 250        # 백분위 계산에 필요한 최소 기록
PERSIST_V2 = 3        # 각 묶음이 며칠 연속 충족돼야 1로 보는지
STRESS_LOOKBACK = 60  # '투매'를 찾는 기간

V2_GROUPS = ["v2_capitulation_ok", "v2_price_ok", "v2_breadth_ok", "v2_foreign_ok",
             "v2_risk_ok", "v2_value_ok", "v2_rates_ok"]
V2_NAMES = {"v2_capitulation_ok": "급락 진정", "v2_price_ok": "저점 상승", "v2_breadth_ok": "시장 폭 개선",
            "v2_foreign_ok": "외국인 순매수", "v2_risk_ok": "글로벌 위험 완화", "v2_value_ok": "밸류에이션",
            "v2_rates_ok": "금리 부담 완화"}
V2_RULES = {
    "v2_capitulation_ok": f"지금 20일 실현변동성이 60일 고점의 0.7배 이하이고, 최근 {STRESS_LOOKBACK}거래일 안에 투매(①252일 고점 대비 -15% 이하 "
                          "②실현변동성 5년 상위 10% ③10일 평균 하락 종목 비율 5년 상위 10% 중 하나)가 있었거나 고점 대비 하락이 -10% 이내",
    "v2_price_ok": "최근 10거래일 동안 60일 신저가가 없고, 코스피가 20일 EMA 위",
    "v2_breadth_ok": "10일 평균 상승 종목 비율이 5년 분포의 상위 30% 이상",
    "v2_foreign_ok": "외국인 순매수 합계가 최근 20거래일·5거래일 모두 플러스",
    "v2_risk_ok": "신용 스프레드·원/달러·VIX 중 2개 이상이 각자 20일 평균보다 낮음",
    "v2_value_ok": "코스피 PBR이 5년 분포 하위 30% 이하, 또는 PER이 5년 분포 하위 20% 이하",
    "v2_rates_ok": "미국 2년물 금리가 63거래일 전보다 낮음",
}
V2_STATES = [("회복 확인", "점수 5 이상 + 저점 상승 충족"), ("바닥 형성", "점수 4 이상"),
             ("바닥 탐색", "점수 3"), ("하락 진행", "점수 2 이하")]


# ---------------------------------------------------------------- KRX 이력 (증분 갱신)
def _merge_save(path: Path, new: pd.DataFrame) -> pd.DataFrame:
    if path.exists():
        old = pd.read_csv(path, dtype={"date": str})
        new = pd.concat([old[~old["date"].isin(new["date"])], new], ignore_index=True)
    new = new.sort_values("date").reset_index(drop=True)
    new.to_csv(path, index=False)
    return new


def update_krx_histories(max_breadth_days: int = 40) -> None:
    """data/의 KRX 이력을 최근 며칠만 새로 받아 덧붙인다. 로그인 정보가 없거나 실패하면 저장된 이력만 쓴다."""
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        print("  KRX_ID/KRX_PW가 없어 KRX 추가 지표는 저장된 이력만 사용")
        return
    try:
        from pykrx import stock
    except ImportError:
        print("  pykrx 없음: KRX 추가 지표는 저장된 이력만 사용")
        return
    DATA.mkdir(exist_ok=True)
    today = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None).normalize()

    def since(path: Path, days: int = 10) -> str:
        if path.exists():
            last = pd.to_datetime(pd.read_csv(path)["date"]).max()
            return (last - pd.Timedelta(days=days)).strftime("%Y%m%d")
        return (today - pd.Timedelta(days=365)).strftime("%Y%m%d")

    try:
        p = DATA / "investor_history.csv"
        inv = stock.get_market_trading_value_by_date(since(p), today.strftime("%Y%m%d"), "KOSPI")
        if inv is not None and len(inv):
            inv.index = pd.to_datetime(inv.index)
            _merge_save(p, pd.DataFrame({"date": inv.index.strftime("%Y-%m-%d"), "foreign": inv["외국인합계"].values,
                                         "institution": inv["기관합계"].values, "individual": inv["개인"].values}))
    except Exception as e:  # noqa: BLE001
        print("  외국인 순매수 갱신 실패:", e)
    try:
        p = DATA / "fundamental_history.csv"
        f = stock.get_index_fundamental(since(p), today.strftime("%Y%m%d"), "1001")
        if f is not None and len(f):
            f.index = pd.to_datetime(f.index)
            _merge_save(p, pd.DataFrame({"date": f.index.strftime("%Y-%m-%d"), "per": f["PER"].values,
                                         "pbr": f["PBR"].values, "div_yield": f["배당수익률"].values}))
    except Exception as e:  # noqa: BLE001
        print("  지수 PER 갱신 실패:", e)
    try:
        p = DATA / "breadth_history.csv"
        days = stock.get_index_ohlcv(since(p, 20), today.strftime("%Y%m%d"), "1001").index
        have = set(pd.read_csv(p, dtype={"date": str})["date"]) if p.exists() else set()
        todo = [d for d in pd.to_datetime(days).strftime("%Y-%m-%d") if d not in have][-max_breadth_days:]
        rows = []
        for d in todo:
            df = stock.get_market_ohlcv_by_ticker(d.replace("-", ""), market="KOSPI")
            ch = df["등락률"]
            if (ch != 0).sum() == 0:  # 장중이라 아직 등락률이 비어 있으면 저장하지 않음
                continue
            rows.append({"date": d, "up": int((ch > 0).sum()), "down": int((ch < 0).sum()), "flat": int((ch == 0).sum())})
            time.sleep(0.2)
        if rows:
            _merge_save(p, pd.DataFrame(rows))
    except Exception as e:  # noqa: BLE001
        print("  시장 폭 갱신 실패:", e)


def load_krx_extra(index: pd.DatetimeIndex) -> pd.DataFrame:
    out = pd.DataFrame(index=index)
    for name, cols in [("breadth_history.csv", ["up", "down", "flat"]), ("investor_history.csv", ["foreign"]),
                       ("fundamental_history.csv", ["per", "pbr"])]:
        p = DATA / name
        if not p.exists():
            for c in cols:
                out[c if c != "pbr" else "pbr_krx"] = np.nan
            continue
        d = pd.read_csv(p, parse_dates=["date"]).set_index("date")
        for c in cols:
            out[c if c != "pbr" else "pbr_krx"] = d[c].reindex(index)
    return out


# ---------------------------------------------------------------- 판정
def _pct_rank(s: pd.Series, win: int = WIN5Y, minp: int = MIN_HIST) -> pd.Series:
    """그날 값이 과거 win일(그날 포함) 분포에서 몇 % 위치인지(0~1). 미래 값은 쓰지 않는다."""
    return s.rolling(win, min_periods=minp).apply(lambda a: (a[:-1] < a[-1]).mean() if len(a) > 1 else np.nan, raw=True)


def _persist(cond: pd.Series, valid: pd.Series, n: int = PERSIST_V2) -> pd.Series:
    c = cond.fillna(False).astype(int)
    s = (c.rolling(n).sum() == n).astype("float64")
    s[~valid.fillna(False).astype(bool)] = np.nan
    return s


def build_v2(df: pd.DataFrame, vix: pd.Series | None) -> pd.DataFrame:
    px = df["kospi"]
    ex = load_krx_extra(df.index)
    vol = df["realized_vol"]
    ema20 = px.ewm(span=20, adjust=False, min_periods=20).mean()

    adv = ex["up"] / (ex["up"] + ex["down"])
    adv10 = adv.rolling(10, min_periods=8).mean()
    dec10 = 1 - adv10
    df["v2_adv_ratio10"] = adv10 * 100

    # 1) 투매 후 진정
    r_vol, r_dec, r_adv = _pct_rank(vol), _pct_rank(dec10), _pct_rank(adv10)
    stress = (df["drawdown_pct"] <= -15) | (r_vol >= 0.9) | (r_dec >= 0.9)
    recent_stress = stress.astype(int).rolling(STRESS_LOOKBACK, min_periods=1).max() == 1
    calm = vol <= vol.rolling(60).max() * 0.7
    # 큰 하락이 없던 구간(고점 대비 -10% 이내)도 진정 상태로 본다. 그렇지 않으면 평온한 상승장이 '하락 진행'으로 잡힘
    cap = (recent_stress | (df["drawdown_pct"] > -10)) & calm
    # 2) 저점 상승
    low60 = px.rolling(60).min()
    no_new_low = px.rolling(10).min() >= low60.shift(10)  # 최근 10일 최저가가 그 전 60일 최저가 이상 = 10일간 신저가 없음
    price = no_new_low & (px > ema20)
    # 3) 시장 폭
    breadth = r_adv >= 0.7
    # 4) 외국인
    fsum20, fsum5 = ex["foreign"].rolling(20, min_periods=18).sum(), ex["foreign"].rolling(5, min_periods=4).sum()
    foreign = (fsum20 > 0) & (fsum5 > 0)
    df["v2_foreign20_bn"] = fsum20 / 1e8  # 억 원
    # 5) 글로벌 위험 완화(묶음)
    cs, fx = df["credit_spread"], df["usdkrw"]
    parts = [cs < cs.rolling(20).mean(), fx < fx.rolling(20).mean()]
    if vix is not None and len(vix):
        v = vix.reindex(df.index.union(vix.index)).ffill().reindex(df.index).shift(1)  # 미국 지표는 하루 늦춤
        df["vix"] = v
        parts.append(v < v.rolling(20).mean())
        vix_valid = v.rolling(20).mean().notna()
    else:
        df["vix"] = np.nan
        vix_valid = pd.Series(False, index=df.index)
    known = cs.rolling(20).mean().notna().astype(int) + fx.rolling(20).mean().notna().astype(int) + vix_valid.astype(int)
    hits = sum(p_.fillna(False).astype(int) for p_ in parts)
    risk = hits >= np.minimum(2, known)  # 자료가 있는 항목 중 2개(1개뿐이면 1개) 이상
    # 6) 밸류에이션 (KRX 공식 PBR·PER, 없으면 v1의 PBR)
    pbr = ex["pbr_krx"].where(ex["pbr_krx"] > 0).fillna(df.get("pbr"))
    per = ex["per"].where(ex["per"] > 0)
    r_pbr, r_per = _pct_rank(pbr), _pct_rank(per)
    value = (r_pbr <= 0.3) | (r_per <= 0.2)
    df["v2_per"] = per
    # 7) 금리 부담 완화
    rates = df["ust2y"] < df["ust2y"].shift(63)

    valid = {
        "v2_capitulation_ok": vol.rolling(60).max().notna(),
        "v2_price_ok": low60.shift(10).notna() & ema20.notna(),
        "v2_breadth_ok": r_adv.notna(),
        "v2_foreign_ok": fsum20.notna(),
        "v2_risk_ok": cs.rolling(20).mean().notna() | fx.rolling(20).mean().notna(),
        "v2_value_ok": r_pbr.notna() | r_per.notna(),
        "v2_rates_ok": df["ust2y"].shift(63).notna(),
    }
    raw = {"v2_capitulation_ok": cap, "v2_price_ok": price, "v2_breadth_ok": breadth, "v2_foreign_ok": foreign,
           "v2_risk_ok": risk, "v2_value_ok": value, "v2_rates_ok": rates}
    for c in V2_GROUPS:
        df[c] = _persist(raw[c], valid[c])

    df["v2_score"] = df[V2_GROUPS].sum(axis=1, min_count=1)
    df["v2_known"] = df[V2_GROUPS].notna().sum(axis=1)

    def judge(r):
        s = r["v2_score"]
        if pd.isna(s) or r["v2_known"] < 5:
            return ""
        if s >= 5 and r["v2_price_ok"] == 1:
            return "회복 확인"
        if s >= 4:
            return "바닥 형성"
        if s >= 3:
            return "바닥 탐색"
        return "하락 진행"

    df["v2_state"] = df.apply(judge, axis=1)
    df["v2_on"] = df["v2_state"].isin(["바닥 형성", "회복 확인"]).astype(int)
    return df


# ---------------------------------------------------------------- 매매 백테스트 (판정이 '하락 진행'이 아닐 때 + 종가 > EMA 60)
def trade_backtest(df: pd.DataFrame, years=(20, 10, 5, 3), cost: float = 0.00015) -> list[dict]:
    px = df["kospi"]
    ret = px.pct_change().fillna(0)
    ema60 = px.ewm(span=60, adjust=False, min_periods=60).mean()
    rules = {
        "기존 판정 + EMA 60": (px > ema60) & (df["state"] != "하락 진행") & (df["state"] != ""),
        "개선안(v2) + EMA 60": (px > ema60) & (df["v2_state"] != "하락 진행") & (df["v2_state"] != ""),
        "기존 판정만": (df["state"] != "하락 진행") & (df["state"] != ""),
        "개선안(v2)만": (df["v2_state"] != "하락 진행") & (df["v2_state"] != ""),
    }
    end = px.index[-1]
    rows = []
    for name, sig in list(rules.items()) + [("단순 보유", None)]:
        row = {"rule": name}
        for y in years:
            idx = px.index[px.index > end - pd.DateOffset(years=y)]
            r = ret.loc[idx].copy()
            r.iloc[0] = 0
            if sig is None:
                eq = 1e7 * (1 - cost) * (1 + r).cumprod()
            else:
                p = sig.shift(1).fillna(False).astype(float).loc[idx].copy()
                p.iloc[0] = 0
                eq = 1e7 * (1 + p * r - p.diff().abs().fillna(0) * cost).cumprod()
            yrs = (idx[-1] - idx[0]).days / 365.25
            row[y] = {"final": eq.iloc[-1], "cagr": (eq.iloc[-1] / 1e7) ** (1 / yrs) - 1,
                      "mdd": (eq / eq.cummax() - 1).min()}
        rows.append(row)
    return rows


# ---------------------------------------------------------------- 매크로 참고 (판정에는 넣지 않음)
MACRO_SERIES = [
    ("XTEXVA01KRM667S", "한국 수출(달러, 월)", "yoy"),
    ("IRSTCI01KRM156N", "한국 콜금리(월 평균)", "chg3"),
    ("IR3TIB01KRM156N", "한국 3개월 금리(월 평균)", "chg3"),
    ("DGS10", "미국 10년물 금리", "chg63"),
    ("DTWEXBGS", "달러 지수(광의)", "pct63"),
]


def macro_snapshot(fred_fn) -> list[dict]:
    out = []
    for sid, name, how in MACRO_SERIES:
        try:
            s = fred_fn(sid).dropna()
            last, d = float(s.iloc[-1]), s.index[-1]
            if how == "yoy":
                prev = s[s.index <= d - pd.DateOffset(years=1)]
                chg, unit = (last / float(prev.iloc[-1]) - 1) * 100 if len(prev) else np.nan, "전년 대비 %"
                val = f"{last / 1e9:,.1f}억 달러"
            elif how == "chg3":
                prev = s[s.index <= d - pd.DateOffset(months=3)]
                chg, unit = (last - float(prev.iloc[-1])) if len(prev) else np.nan, "3개월 변화 %p"
                val = f"{last:.2f}%"
            elif how == "chg63":
                chg, unit = last - float(s.iloc[-64]) if len(s) > 64 else np.nan, "약 3개월 변화 %p"
                val = f"{last:.2f}%"
            else:
                chg, unit = (last / float(s.iloc[-64]) - 1) * 100 if len(s) > 64 else np.nan, "약 3개월 변화 %"
                val = f"{last:.1f}"
            out.append({"id": sid, "name": name, "date": f"{d:%Y-%m-%d}", "value": val, "chg": chg, "unit": unit})
        except Exception as e:  # noqa: BLE001
            out.append({"id": sid, "name": name, "date": "–", "value": "가져오지 못함", "chg": np.nan, "unit": str(e)[:60]})
    return out


# ---------------------------------------------------------------- 리포트
def report_v2(df: pd.DataFrame, eps: list[dict], score_fn, pct_fn, macro: list[dict], trades: list[dict]) -> list[str]:
    last = df[df["v2_state"] != ""].iloc[-1]
    L = ["## 개선안(v2) 판정 — 기존 판정과 나란히 비교 중", "",
         f"- 판정: **{last['v2_state']}** (점수 {int(last['v2_score'])} / {int(last['v2_known'])}, {last.name:%Y-%m-%d})",
         f"- 기존 판정: {last['state']}", "",
         "| 묶음 | 상태 | 기준 |", "|---|---|---|"]
    for c in V2_GROUPS:
        v = last[c]
        L.append(f"| {V2_NAMES[c]} | {'충족' if v == 1 else '미충족' if v == 0 else '자료 없음'} | {V2_RULES[c]} |")
    L += ["", f"각 묶음은 {PERSIST_V2}거래일 연속 충족돼야 1로 봅니다. 백분위는 그날까지 약 5년({WIN5Y}거래일) 값으로만 계산합니다.", "",
          "단계: " + " · ".join(f"**{a}** {b}" for a, b in V2_STATES), "",
          "기존 판정과 달라진 점: 126일선 대신 저점 상승·시장 폭을 쓰고, 투매 후 진정과 외국인 수급을 넣었으며, "
          "신용 스프레드·환율·VIX는 한 묶음으로 셌습니다. 임계값은 결과를 보기 전에 정한 초기값입니다.", ""]

    L += ["### 하락 구간별 신호 성적: 기존 vs 개선안", "",
          "신호는 기존이 '바닥 확인 중·회복', 개선안이 '바닥 형성·회복 확인'으로 바뀐 날입니다.", "",
          "| 구간 | 최대 하락 | 기존 헛신호 | 기존 추가 하락 | 기존 지연 | 개선안 헛신호 | 개선안 추가 하락 | 개선안 지연 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    agg = {"v1": [], "v2": []}
    for e in eps:
        a, b = score_fn(df, e, "model_on"), score_fn(df, e, "v2_on")
        ongoing = e["end"] is None
        if not ongoing:
            agg["v1"].append(a)
            agg["v2"].append(b)
        lab = f"{e['peak']:%Y.%m}–{e['trough']:%Y.%m}" + (" (진행 중)" if ongoing else "")
        lag = lambda m: "–" if m["lag"] is None else f"{m['lag']}일"  # noqa: E731
        L.append(f"| {lab} | {pct_fn(e['max_dd'])} | {a['false_n']} | {pct_fn(a['worst_fall'])} | {lag(a)} | "
                 f"{b['false_n']} | {pct_fn(b['worst_fall'])} | {lag(b)} |")

    def summ(rows):
        lags = [r["lag"] for r in rows if r["lag"] is not None]
        falls = [r["worst_fall"] for r in rows if r["worst_fall"] is not None]
        return sum(r["false_n"] for r in rows), (np.median(lags) if lags else None), (np.mean(falls) if falls else None)
    (f1, l1, w1), (f2, l2, w2) = summ(agg["v1"]), summ(agg["v2"])
    fmt_l = lambda v: "–" if v is None else f"{v:.0f}일"  # noqa: E731
    L += ["", "| 합계 (끝난 하락 구간) | 기존 | 개선안 |", "|---|---:|---:|",
          f"| 헛신호 합계 | {f1} | {f2} |", f"| 헛신호 후 추가 하락 (평균) | {pct_fn(w1)} | {pct_fn(w2)} |",
          f"| 저점 후 지연 (중앙값) | {fmt_l(l1)} | {fmt_l(l2)} |", ""]

    years = [k for k in trades[0] if k != "rule"]
    L += ["### 매매 백테스트: 기존 vs 개선안", "",
          "1,000만 원, 판정이 '하락 진행'이 아닐 때(EMA 60 규칙은 종가가 60일 EMA 위일 때도) 보유. 다음 거래일 체결, 매수·매도 각 0.015%, 현금 이자·배당 미반영. "
          "최종 금액(괄호 안은 최대 낙폭).", "",
          "| 규칙 | " + " | ".join(f"{y}년" for y in years) + " |", "|---|" + "---:|" * len(years)]
    for r in trades:
        L.append(f"| {r['rule']} | " + " | ".join(f"{r[y]['final'] / 1e4:,.0f}만 원 ({r[y]['mdd'] * 100:.1f}%)" for y in years) + " |")
    L.append("")

    L += ["## 매크로 참고 (판정에는 넣지 않음)", "",
          "월별 자료는 발표가 1~2개월 늦습니다. 반도체 수출, 이익 전망(선행 PER·EPS 조정), 신용융자 잔고, VKOSPI, 한국 소비자물가는 "
          "무료 자동 수집 소스를 찾지 못해 빠져 있습니다(FRED의 한국 CPI는 2023-11에서 갱신이 멈춤).", "",
          "| 지표 | 기준일 | 값 | 변화 |", "|---|---|---:|---:|"]
    for m in macro:
        chg = "–" if pd.isna(m["chg"]) else f"{m['chg']:+.2f} ({m['unit']})"
        L.append(f"| {m['name']} | {m['date']} | {m['value']} | {chg} |")
    L.append("")
    return L
