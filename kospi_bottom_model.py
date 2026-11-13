"""코스피 바닥 신호 모델.

공개 데이터로 다섯 가지 체크 항목을 매일 계산해 판정을 내리고,
2002년 이후 큰 하락 구간에서 신호가 얼마나 일찍(헛신호)·늦게(지연) 켜졌는지 잽니다.

실행:  pip install pandas numpy
       python kospi_bottom_model.py
결과:  signals_daily.csv, report.md (같은 폴더)

참고용 분석이며 매수·매도 판단이나 투자 자문이 아닙니다.
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
START = "2000-01-01"
UA = {"User-Agent": "Mozilla/5.0 (kospi-bottom-model)"}

# ---- 파라미터 (검증 전 초기값: 결과를 보고 맞추면 과적합) ----
PERSIST = 5          # 조건이 며칠 연속 충족돼야 신호로 보는지
MA_DAYS = 126        # 6개월 이동평균
VOL_DAYS = 20        # 실현변동성 창
VOL_RATIO = 0.7      # 변동성이 최근 60일 고점의 몇 배 이하이면 '진정'
TIGHT_LAG = 63       # 2년물 금리를 몇 거래일 전과 비교할지 (약 3개월)
PBR_WINDOW = 1250    # PBR 저평가 판단에 쓰는 과거 기간 (약 5년)
PBR_MIN_DAYS = 250   # 이 기간보다 기록이 짧으면 PBR 항목은 '자료 없음'
PBR_PCT = 0.2        # PBR이 과거 기간의 하위 20% 이하이면 '저평가'
DD_EPISODE = -0.20   # 252일 고점 대비 이 이상 하락하면 하락 구간
EPISODE_FROM = "2002-01-01"


def http_get(url: str, tries: int = 3) -> bytes:
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            print(f"  재시도 {k + 1}: {e}")
            time.sleep(3)
    raise RuntimeError("unreachable")


def yahoo(ticker: str) -> pd.Series:
    p1 = int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time()) + 86400
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(ticker)}?period1={p1}&period2={p2}&interval=1d"
    j = json.loads(http_get(url))["chart"]["result"][0]
    gmt = j["meta"].get("gmtoffset", 0)
    idx = pd.to_datetime([t + gmt for t in j["timestamp"]], unit="s").normalize()
    s = pd.Series(j["indicators"]["quote"][0]["close"], index=idx, dtype="float64")
    s = s[~s.index.duplicated(keep="last")].dropna()
    return s


def naver_kospi() -> pd.Series:
    """네이버 금융 일봉(KRX 종가, 최근 약 3000거래일)."""
    import re
    raw = http_get("https://fchart.stock.naver.com/sise.nhn?symbol=KOSPI&timeframe=day&count=3000&requestType=0")
    rows = re.findall(r'data="(\d{8})\|[^|]*\|[^|]*\|[^|]*\|([^|]*)\|', raw.decode("euc-kr", errors="ignore"))
    s = pd.Series({pd.Timestamp(d): float(c) for d, c in rows}, dtype="float64")
    return s.sort_index()


def previous_kospi() -> pd.Series:
    """지난번에 저장한 코스피 전체 이력 (Yahoo가 막혔을 때 과거 구간 대체용)."""
    prev = pd.read_csv(OUT / "kospi_history.csv", index_col=0, parse_dates=True)["kospi"]
    return prev.dropna()


def kospi_series() -> tuple[pd.Series, str]:
    try:
        y, ysrc = yahoo("^KS11"), "Yahoo Finance ^KS11"
    except Exception as e:  # noqa: BLE001
        print("  Yahoo 실패, 저장해 둔 kospi_history.csv 사용:", e)
        y, ysrc = previous_kospi(), "저장해 둔 이력(원출처 Yahoo Finance ^KS11)"
    try:
        n = naver_kospi()
        s = pd.concat([y[y.index < n.index[0]], n])
        src = f"{ysrc}(~{n.index[0]:%Y-%m-%d} 이전) + 네이버 금융 KRX 종가(이후)"
    except Exception as e:  # noqa: BLE001
        print("  네이버 실패, Yahoo만 사용:", e)
        s, src = y, f"{ysrc} 종가"
    # 장중에 실행하면 오늘 값은 종가가 아니므로 뺀다 (KRX 마감 15:30 KST)
    now_kst = pd.Timestamp.now(tz="Asia/Seoul")
    if s.index[-1].date() == now_kst.date() and (now_kst.hour, now_kst.minute) < (15, 40):
        s = s.iloc[:-1]
    return s, src


def fred(series_id: str) -> pd.Series:
    raw = http_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={START}")
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = ["date", "v"]
    df["date"] = pd.to_datetime(df["date"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.dropna().set_index("date")["v"]


PBR_FILE = OUT / "pbr_history.csv"


def kospi_pbr() -> dict:
    """코스피 PBR 추정치: 네이버 종목별 시가총액·PBR로 '시가총액 합 ÷ 순자산 합'을 계산.

    KRX 공식 지수 PBR은 정보데이터시스템 로그인이 필요해 직접 받을 수 없다.
    보통주만 쓰고(우선주·ETF·ETN 제외), PBR이 없거나 0 이하(자본잠식)인 종목은 뺀다.
    """
    import concurrent.futures as cf
    import re

    def num(s):
        return float(re.sub(r"[^0-9.\-]", "", s)) if s and re.search(r"\d", s) else None

    stocks, page = [], 1
    while page <= 40:
        j = json.loads(http_get(f"https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page={page}&pageSize=100"))
        if not j.get("stocks"):
            break
        stocks += j["stocks"]
        page += 1
    common = [s for s in stocks if s.get("stockEndType") == "stock" and not re.search(r"우[A-C]?$|우\(전환\)$", s["stockName"])]
    total_mc = sum(num(s["marketValue"]) or 0 for s in common)

    def one(s):
        try:
            j = json.loads(http_get(f"https://m.stock.naver.com/api/stock/{s['itemCode']}/integration"))
            d = {x["code"]: x["value"] for x in j.get("totalInfos", [])}
            return num(s["marketValue"]), num(d.get("pbr"))
        except Exception:  # noqa: BLE001
            return num(s["marketValue"]), None

    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, common))
    used = [(mc, p) for mc, p in res if mc and p and p > 0]
    mc = sum(m for m, _ in used)
    book = sum(m / p for m, p in used)
    now = pd.Timestamp.now(tz="Asia/Seoul")
    return {"date": now.strftime("%Y-%m-%d"), "pbr": round(mc / book, 3), "coverage": round(mc / total_mc, 3),
            "n_stocks": len(used), "time_kst": now.strftime("%H:%M"),
            "intraday": int((now.hour, now.minute) < (15, 40) and now.weekday() < 5)}


PBR_COLS = ["date", "pbr", "source", "coverage", "n_stocks", "time_kst", "intraday"]


def krx_pbr(hist: pd.DataFrame) -> pd.DataFrame | None:
    """KRX 공식 코스피 PBR (정보데이터시스템, 로그인 필요).

    환경변수 KRX_ID / KRX_PW가 있을 때만 pykrx로 받는다. 처음에는 2000년부터 전부,
    그 뒤로는 마지막 KRX 기록 10일 전부터만 받아 덮어쓴다.
    """
    import os
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        print("  KRX_ID/KRX_PW가 없어 KRX 공식 PBR은 건너뜀")
        return None
    try:
        from pykrx import stock
    except ImportError:
        print("  pykrx가 설치돼 있지 않아 KRX 공식 PBR은 건너뜀 (pip install pykrx)")
        return None
    krx_dates = pd.to_datetime(hist.loc[hist["source"] == "KRX", "date"])
    start = (krx_dates.max() - pd.Timedelta(days=10)) if len(krx_dates) else pd.Timestamp(START)
    end = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None).normalize()
    frames, a = [], start
    while a <= end:  # KRX는 한 번에 긴 기간을 주지 않을 수 있어 1년씩 나눠 받는다
        b = min(a + pd.Timedelta(days=364), end)
        df = stock.get_index_fundamental(a.strftime("%Y%m%d"), b.strftime("%Y%m%d"), "1001")
        if df is not None and len(df) and "PBR" in df:
            frames.append(df[["PBR"]])
        a = b + pd.Timedelta(days=1)
        time.sleep(0.5)
    if not frames:
        raise RuntimeError("KRX에서 PBR을 하나도 받지 못함 (로그인 실패 또는 응답 형식 변경)")
    df = pd.concat(frames)
    df = df[df["PBR"] > 0]
    out = pd.DataFrame({"date": pd.to_datetime(df.index).strftime("%Y-%m-%d"), "pbr": df["PBR"].round(3).values})
    out["source"], out["intraday"] = "KRX", 0
    print(f"  KRX 공식 PBR {len(out)}일치 ({out['date'].iloc[0]} ~ {out['date'].iloc[-1]})")
    return out


def update_pbr_history() -> pd.DataFrame:
    """pbr_history.csv 갱신. 같은 날짜는 KRX 공식 값이 네이버 추정치보다 우선."""
    hist = pd.read_csv(PBR_FILE, dtype={"date": str}) if PBR_FILE.exists() else pd.DataFrame(columns=PBR_COLS)
    if "source" not in hist:
        hist["source"] = "naver_est"
    hist["source"] = hist["source"].fillna("naver_est")
    print("코스피 PBR")
    try:
        k = krx_pbr(hist)
        if k is not None:
            hist = pd.concat([hist[~hist["date"].isin(k["date"])], k], ignore_index=True)
    except Exception as e:  # noqa: BLE001
        print("  KRX 공식 PBR 실패, 이전 기록 유지:", e)
    try:
        row = kospi_pbr()
        if row["coverage"] < 0.8:
            raise RuntimeError(f"시가총액 커버리지가 {row['coverage']:.0%}로 낮아 저장하지 않음")
        row["source"] = "naver_est"
        if not ((hist["date"] == row["date"]) & (hist["source"] == "KRX")).any():
            hist = pd.concat([hist[hist["date"] != row["date"]], pd.DataFrame([row])], ignore_index=True)
        print(f"  네이버 추정 PBR {row['pbr']} (보통주 {row['n_stocks']}종목, 시총 {row['coverage']:.1%})")
    except Exception as e:  # noqa: BLE001
        print("  네이버 추정 PBR 실패:", e)
    hist = hist.reindex(columns=PBR_COLS).sort_values("date").reset_index(drop=True)
    hist.to_csv(PBR_FILE, index=False)
    return hist


def persist(cond: pd.Series, n: int = PERSIST) -> pd.Series:
    """n거래일 연속 True일 때만 1."""
    c = cond.fillna(False).astype(int)
    return (c.rolling(n).sum() == n).astype(int)


def load() -> tuple[pd.DataFrame, dict]:
    notes = {}
    print("코스피 지수 (Yahoo ^KS11 + 네이버 금융)")
    kospi, notes["kospi"] = kospi_series()
    print("원/달러 환율 (Yahoo KRW=X)")
    try:
        krw = yahoo("KRW=X")
        notes["fx"] = "원/달러 환율(Yahoo KRW=X, 2003-12부터)"
    except Exception as e:  # noqa: BLE001
        print("  Yahoo 실패, FRED DEXKOUS로 대체:", e)
        krw = fred("DEXKOUS")
        notes["fx"] = "원/달러 환율(FRED DEXKOUS, Yahoo 접속 실패로 대체. 며칠 늦게 갱신됨)"
    print("미국 2년물 금리 (FRED DGS2)")
    dgs2 = fred("DGS2")
    print("미국 하이일드 스프레드 (FRED BAMLH0A0HYM2)")
    try:
        hy = fred("BAMLH0A0HYM2")
    except Exception as e:  # noqa: BLE001
        print("  실패:", e)
        hy = pd.Series(dtype="float64")
    if len(hy) and hy.index[0] <= pd.Timestamp(EPISODE_FROM):
        credit, notes["credit"] = hy, "미국 하이일드 스프레드(ICE BofA, FRED BAMLH0A0HYM2)"
    else:
        print(f"  하이일드 이력이 {hy.index[0].date() if len(hy) else '없음'}부터라 짧음 → Baa 스프레드(FRED BAA10Y)로 대체")
        credit = fred("BAA10Y")
        notes["credit"] = "미국 Baa 회사채 − 10년물 스프레드(FRED BAA10Y). 하이일드 스프레드는 FRED에서 최근 3년치만 제공돼 대체함"

    df = pd.DataFrame({"kospi": kospi})
    df = df[df.index >= START]
    # 미국 지표는 한국 장 마감 뒤에 나오므로 하루 늦춰 붙인다(미리 보기 방지).
    for name, s in [("usdkrw", krw), ("ust2y", dgs2), ("credit_spread", credit)]:
        s = s.reindex(df.index.union(s.index)).ffill()
        df[name] = s.reindex(df.index).shift(0 if name == "usdkrw" and "Yahoo" in notes["fx"] else 1)
    return df, notes


COND_COLS = ["credit_ok", "fx_ok", "tightening_ok", "ma6m_ok", "vol_ok", "pbr_ok"]


def build(df: pd.DataFrame, pbr: pd.Series | None = None) -> pd.DataFrame:
    px = df["kospi"]
    # PBR: 장 마감 후 값만(KRX 공식 우선). 빠진 날은 최대 3거래일까지 직전 값으로 채움
    df["pbr"] = pbr.reindex(df.index).ffill(limit=3) if pbr is not None else np.nan
    df["ma6m"] = px.rolling(MA_DAYS).mean()
    ret = np.log(px).diff()
    df["realized_vol"] = ret.rolling(VOL_DAYS).std() * np.sqrt(252) * 100
    df["high_252"] = px.rolling(252, min_periods=60).max()
    df["drawdown_pct"] = (px / df["high_252"] - 1) * 100

    cs = df["credit_spread"]
    raw = pd.DataFrame(index=df.index)
    raw["credit_ok"] = (cs < cs.rolling(20).mean()) & (cs <= cs.rolling(60).max() * 0.9)
    fx = df["usdkrw"]
    raw["fx_ok"] = fx < fx.rolling(20).mean()
    raw["tightening_ok"] = df["ust2y"] < df["ust2y"].shift(TIGHT_LAG)
    raw["ma6m_ok"] = px > df["ma6m"]
    vol = df["realized_vol"]
    raw["vol_ok"] = vol <= vol.rolling(60).max() * VOL_RATIO
    pb = df["pbr"]
    pb_cut = pb.rolling(PBR_WINDOW, min_periods=PBR_MIN_DAYS).quantile(PBR_PCT)
    raw["pbr_ok"] = pb <= pb_cut
    df["pbr_cut"] = pb_cut

    for c in raw:
        valid = {"credit_ok": cs, "fx_ok": fx, "tightening_ok": df["ust2y"].shift(TIGHT_LAG),
                 "ma6m_ok": df["ma6m"], "vol_ok": vol.rolling(60).max(), "pbr_ok": pb_cut}[c].notna()
        s = persist(raw[c]).astype("float64")
        s[~valid] = np.nan
        df[c] = s

    conds = COND_COLS
    df["conditions_met"] = df[conds].sum(axis=1, min_count=1)
    df["conditions_known"] = df[conds].notna().sum(axis=1)

    def judge(r):
        s, m = r["conditions_met"], r["ma6m_ok"]
        if pd.isna(s) or r["conditions_known"] < 4:
            return ""
        if s >= 4 and m == 1:
            return "회복"
        if s >= 3:
            return "바닥 확인 중"
        if s == 2:
            return "단기 반등 가능"
        return "하락 진행"

    df["state"] = df.apply(judge, axis=1)
    df["model_on"] = df["state"].isin(["바닥 확인 중", "회복"]).astype(int)
    df["ma_only_on"] = df["ma6m_ok"].fillna(0).astype(int)
    return df


def episodes(df: pd.DataFrame) -> list[dict]:
    px = df["kospi"]
    out, i, idx = [], 0, df.index
    n = len(df)
    while i < n:
        if idx[i] < pd.Timestamp(EPISODE_FROM) or not (df["drawdown_pct"].iat[i] <= DD_EPISODE * 100):
            i += 1
            continue
        peak_val = df["high_252"].iat[i]
        win = px.iloc[max(0, i - 252): i + 1]
        peak_date = win[win == peak_val].index[-1]
        j = i
        while j < n and px.iat[j] < peak_val:
            j += 1
        seg = px.loc[peak_date: idx[min(j, n - 1)]]
        trough_date = seg.idxmin()
        out.append({
            "peak": peak_date, "peak_val": peak_val, "trough": trough_date, "trough_val": seg.min(),
            "end": idx[j] if j < n else None, "max_dd": seg.min() / peak_val - 1,
        })
        i = j + 1
    return out


def score(df: pd.DataFrame, ep: dict, col: str) -> dict:
    s = df[col]
    px = df["kospi"]
    edges = (s == 1) & (s.shift(1, fill_value=0) == 0)
    before = edges.loc[ep["peak"]: ep["trough"]]
    before = before[before].index.drop(ep["trough"], errors="ignore")
    falls = [ep["trough_val"] / px.loc[d] - 1 for d in before]
    after = s.loc[ep["trough"]:]
    on_after = after[after == 1]
    if len(on_after):
        first = on_after.index[0]
        lag = df.index.get_loc(first) - df.index.get_loc(ep["trough"])
        gain = px.loc[first] / ep["trough_val"] - 1
    else:
        first, lag, gain = None, None, None
    return {"false_n": len(before), "worst_fall": min(falls) if falls else None,
            "first": first, "lag": lag, "gain_missed": gain}


def pct(v, signed=True):
    return "–" if v is None or pd.isna(v) else (f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%")


def write_report(df: pd.DataFrame, eps: list[dict], notes: dict, pbr: pd.DataFrame | None = None,
                 extra: list[str] | None = None) -> str:
    last = df.dropna(subset=["state"]).iloc[-1]
    d = last.name.date()
    names = {"credit_ok": "신용 안정", "fx_ok": "외환 안정", "tightening_ok": "긴축 둔화", "ma6m_ok": "6개월선 회복", "vol_ok": "변동성 진정", "pbr_ok": "PBR 저평가"}
    L = [f"# 코스피 바닥 신호 리포트", "",
         f"생성: {pd.Timestamp.now(tz='Asia/Seoul'):%Y-%m-%d %H:%M} KST · 데이터 마지막 날짜: **{d}** · 참고용 분석이며 투자 자문이 아닙니다.", "",
         "## 현재 상태", "",
         f"- 코스피: **{last['kospi']:,.2f}** (252일 고점 대비 {last['drawdown_pct']:+.1f}%)",
         f"- 판정: **{last['state']}** (체크 항목 {int(last['conditions_met'])} / {int(last['conditions_known'])} 충족)"]
    if pbr is not None and len(pbr):
        p = pbr.iloc[-1]
        when = f"{p['date']} {p['time_kst'] if isinstance(p['time_kst'], str) else ''}".strip() + (" 장중" if int(p["intraday"]) else "")
        lc = df["pbr_cut"].dropna()
        cut = f". 저평가 기준선(최근 5년 하위 {int(PBR_PCT * 100)}%): {lc.iloc[-1]:.2f}배" if len(lc) else ""
        if p["source"] == "KRX":
            L.append(f"- 코스피 PBR: **{float(p['pbr']):.2f}배** ({p['date']} KRX 공식){cut}")
        else:
            L.append(f"- 코스피 PBR(추정): **{float(p['pbr']):.2f}배** ({when} 기준, 네이버 종목별 PBR로 계산, 보통주 {int(p['n_stocks'])}종목·시가총액 {float(p['coverage']):.0%} 반영){cut}")
    L.append("")
    L += ["| 항목 | 상태 | 기준 |", "|---|---|---|"]
    rule = {"credit_ok": "스프레드가 20일 평균보다 낮고 60일 고점의 0.9배 이하",
            "fx_ok": "원/달러가 20일 평균보다 낮음",
            "tightening_ok": f"미국 2년물이 {TIGHT_LAG}거래일 전보다 낮음",
            "ma6m_ok": f"코스피가 {MA_DAYS}일 이동평균 위",
            "vol_ok": f"{VOL_DAYS}일 실현변동성이 60일 고점의 {VOL_RATIO}배 이하",
            "pbr_ok": f"코스피 PBR이 최근 약 5년({PBR_WINDOW}거래일) 값의 하위 {int(PBR_PCT * 100)}% 이하"}
    for c, nm in names.items():
        v = last[c]
        L.append(f"| {nm} | {'충족' if v == 1 else '미충족' if v == 0 else '자료 없음'} | {rule[c]} |")
    L += ["", f"모든 항목은 {PERSIST}거래일 연속 충족돼야 1로 봅니다.", ""]

    L += ["## 판정 규칙", "",
          f"체크 항목은 {len(COND_COLS)}개입니다. 자료가 없는 항목(예: 2003년 이전 외환, 2003년 이전 PBR)은 빼고 셉니다.", "",
          "- **회복**: 4개 이상 충족 + 6개월선 위",
          "- **바닥 확인 중**: 3개 이상 충족",
          "- **단기 반등 가능**: 2개 충족",
          "- **하락 진행**: 1개 이하", "",
          "아래 성적표의 '모델 신호'는 판정이 바닥 확인 중 또는 회복으로 바뀐 날입니다.", ""]

    L += [f"## 하락 구간별 신호 성적 ({EPISODE_FROM[:4]}년 이후, 252일 고점 대비 {int(-DD_EPISODE * 100)}% 이상 하락)", "",
          "헛신호는 고점과 저점 사이에 켜진 신호 수, '헛신호 후 추가 하락'은 그중 가장 나빴던 경우 신호일 종가 대비 저점까지 더 빠진 폭입니다. "
          "지연은 저점 후 첫 신호까지의 거래일 수, '놓친 상승'은 그사이 저점 대비 오른 폭입니다.", "",
          "| 구간 | 고점 | 저점 | 최대 하락 | 모델 헛신호 | 헛신호 후 추가 하락 | 모델 지연 | 놓친 상승 | 6개월선 헛신호 | 6개월선 추가 하락 | 6개월선 지연 | 놓친 상승 |",
          "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    agg = {"model": [], "ma": []}
    for e in eps:
        m, a = score(df, e, "model_on"), score(df, e, "ma_only_on")
        ongoing = e["end"] is None
        if not ongoing:
            agg["model"].append(m)
            agg["ma"].append(a)
        lab = f"{e['peak']:%Y.%m}–{e['trough']:%Y.%m}" + (" (진행 중, 저점 미확정)" if ongoing else "")
        L.append("| " + " | ".join([
            lab, f"{e['peak']:%Y-%m-%d}", f"{e['trough']:%Y-%m-%d}", pct(e["max_dd"]),
            str(m["false_n"]), pct(m["worst_fall"]), "–" if m["lag"] is None else f"{m['lag']}일", pct(m["gain_missed"]),
            str(a["false_n"]), pct(a["worst_fall"]), "–" if a["lag"] is None else f"{a['lag']}일", pct(a["gain_missed"]),
        ]) + " |")
    L.append("")

    def summ(rows):
        lags = [r["lag"] for r in rows if r["lag"] is not None]
        falls = [r["worst_fall"] for r in rows if r["worst_fall"] is not None]
        return (sum(r["false_n"] for r in rows), np.median(lags) if lags else None,
                np.mean(falls) if falls else None)

    mf, ml, mw = summ(agg["model"])
    af, al, aw = summ(agg["ma"])
    done = len(agg["model"])
    L += ["## 6개월 이동평균 단독 신호와 비교", "",
          "진행 중인 하락 구간은 저점이 확정되지 않아 합계에서 뺐습니다.", "",
          "| 지표 | 모델 | 6개월선 단독 |", "|---|---:|---:|",
          f"| 끝난 하락 구간 수 | {done} | {done} |",
          f"| 헛신호 합계 | {mf} | {af} |",
          f"| 헛신호 후 추가 하락 (평균) | {pct(mw)} | {pct(aw)} |",
          f"| 저점 후 지연 (중앙값) | {'–' if ml is None else f'{ml:.0f}일'} | {'–' if al is None else f'{al:.0f}일'} |", ""]

    L += extra or []
    L += ["## 데이터", "",
          f"- 코스피 지수: {notes['kospi']}. 장중(15:40 전)에 실행하면 오늘 값은 제외",
          f"- 신용: {notes['credit']}",
          f"- 외환: {notes['fx']}. 자료가 없는 초기 기간은 외환 항목을 빼고 계산",
          "- 긴축: 미국 2년물 국채금리(FRED DGS2)",
          "- 변동성: VKOSPI 대신 코스피 20일 실현변동성(연율화)",
          "- 미국 지표는 한국 장 마감 후 발표되므로 하루 늦춰 반영",
          "- PBR: KRX 정보데이터시스템 공식 코스피 PBR(로그인 필요, KRX_ID/KRX_PW 설정 시). 그날 KRX 값이 아직 없으면 "
          "네이버 증권 종목별 시가총액·PBR로 계산한 추정치(시가총액 합 ÷ 순자산 합, 보통주만)를 쓰고, 다음 실행 때 공식 값으로 바뀜", "",
          "## 한계", "",
          "- 개선안(v2) 추가 자료: 시장 폭(날짜별 상승·하락 종목 수), 외국인 순매수, 코스피 PER은 KRX 정보데이터시스템(pykrx, 로그인 필요)에서 받아 data/에 저장, VIX는 FRED VIXCLS(하루 늦춰 반영)",
          "- 이익 전망(EPS 조정·선행 PER), VKOSPI, 신용융자 잔고, 국내 회사채 스프레드는 무료 자동 수집 소스가 없어 빠져 있습니다. ",
          "- PBR 저평가 기준(최근 5년 하위 20%)은 결과를 보기 전에 정한 값입니다. 2026-11-12에 체크 항목에 추가했고, 과거 성적표도 같은 규칙으로 다시 계산한 것입니다.",
          "- 임계값(연속 일수, 0.9배, 0.7배 등)은 검증 전 초기값입니다. 결과에 맞춰 조정하면 과적합이 됩니다.",
          "- 하락 구간은 사후에 정의한 것이라 실제 실시간 판단보다 유리하게 보일 수 있습니다.", ""]
    return "\n".join(L)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    df, notes = load()
    pbr = update_pbr_history()
    closed = pbr[pbr["intraday"].fillna(0).astype(int) == 0] if len(pbr) else pbr
    pbr_s = closed.set_index(pd.to_datetime(closed["date"]))["pbr"].astype(float) if len(closed) else None
    df = build(df, pbr_s)
    import bottom_v2 as v2
    print("개선안(v2) 추가 자료 (KRX 시장 폭·외국인·PER, FRED VIX)")
    v2.update_krx_histories()
    try:
        vix = fred("VIXCLS")
    except Exception as e:  # noqa: BLE001
        print("  VIX 실패:", e)
        vix = None
    df = v2.build_v2(df, vix)
    eps = episodes(df)
    extra = v2.report_v2(df, eps, score, pct, v2.macro_snapshot(fred), v2.trade_backtest(df))
    cols = ["kospi", "state", "conditions_met", *COND_COLS,
            "drawdown_pct", "credit_spread", "usdkrw", "ust2y", "realized_vol", "ma6m", "pbr", "pbr_cut",
            "v2_state", "v2_score", *v2.V2_GROUPS, "v2_adv_ratio10", "v2_foreign20_bn", "vix", "v2_per"]
    out = df[cols].copy()
    out = out[out["state"] != ""]
    out.index.name = "date"
    for c in [*COND_COLS, "conditions_met", *v2.V2_GROUPS, "v2_score"]:
        out[c] = out[c].astype("Int64")
    out.round(3).to_csv(OUT / "signals_daily.csv", date_format="%Y-%m-%d")
    df[["kospi"]].rename_axis("date").round(2).to_csv(OUT / "kospi_history.csv", date_format="%Y-%m-%d")
    (OUT / "report.md").write_text(write_report(df, eps, notes, pbr, extra), encoding="utf-8")
    last = out.iloc[-1]
    print(f"\n완료: {len(out)}행, 마지막 {out.index[-1].date()} · 판정 {last['state']} · 하락 구간 {len(eps)}개")
    print(f"→ {OUT / 'signals_daily.csv'}\n→ {OUT / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
