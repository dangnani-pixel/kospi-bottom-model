"""코스피·코스닥 일별 시가·고가·저가·종가 (kospi_ohlc.csv, kosdaq_ohlc.csv). 사이트의 주봉 캔들에 쓴다.

네이버 금융 일봉(최근 약 3000거래일)에 그 이전은 Yahoo Finance(^KS11, ^KQ11)를 이어 붙인다.
Yahoo가 막히면 지난번에 저장한 파일의 과거 구간을 쓴다. 장중(15:40 KST 전)에 실행하면 오늘 값은 뺀다.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from kospi_bottom_model import OUT, START, http_get

COLS = ["open", "high", "low", "close"]


def naver_ohlc(symbol: str) -> pd.DataFrame:
    raw = http_get(f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=3000&requestType=0")
    rows = re.findall(r'data="(\d{8})\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|', raw.decode("euc-kr", errors="ignore"))
    df = pd.DataFrame(rows, columns=["date", *COLS])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[COLS].astype(float).sort_index()


def yahoo_ohlc(ticker: str) -> pd.DataFrame:
    p1 = int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time()) + 86400
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(ticker)}?period1={p1}&period2={p2}&interval=1d"
    j = json.loads(http_get(url))["chart"]["result"][0]
    gmt = j["meta"].get("gmtoffset", 0)
    idx = pd.to_datetime([t + gmt for t in j["timestamp"]], unit="s").normalize()
    q = j["indicators"]["quote"][0]
    df = pd.DataFrame({c: q[c] for c in COLS}, index=idx, dtype="float64")
    return df[~df.index.duplicated(keep="last")].dropna(subset=["close"])


def build(name: str, naver_sym: str, yahoo_sym: str) -> None:
    path = OUT / f"{name}_ohlc.csv"
    n = naver_ohlc(naver_sym)
    try:
        old = yahoo_ohlc(yahoo_sym)
    except Exception as e:  # noqa: BLE001
        print(f"  Yahoo {yahoo_sym} 실패, 저장된 이력 사용:", e)
        old = pd.read_csv(path, index_col=0, parse_dates=True) if path.exists() else pd.DataFrame(columns=COLS)
    df = pd.concat([old[old.index < n.index[0]], n])
    df = df[df["close"] > 0]
    # 시가·고가·저가가 비었거나 0이면 종가로 채움(오래된 Yahoo 자료에 가끔 있음)
    for c in ["open", "high", "low"]:
        df[c] = df[c].where(df[c] > 0, df["close"])
    df["high"] = df[COLS].max(axis=1)
    df["low"] = df[COLS].min(axis=1)
    now = pd.Timestamp.now(tz="Asia/Seoul")
    if df.index[-1].date() == now.date() and (now.hour, now.minute) < (15, 40):
        df = df.iloc[:-1]
    df.rename_axis("date").round(2).to_csv(path, date_format="%Y-%m-%d")
    print(f"{name} OHLC {len(df)}일 ({df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d})")


def main() -> int:
    ok = True
    for args in [("kospi", "KOSPI", "^KS11"), ("kosdaq", "KOSDAQ", "^KQ11")]:
        try:
            build(*args)
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"{args[0]} OHLC 실패:", e)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
