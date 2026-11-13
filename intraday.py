"""장중 코스피 잠정 신호.

장중(평일 09:00~15:40 KST)에 네이버 금융 일봉의 오늘 값(아직 종가 아님)을 받아
'종가 > EMA 60 + 판정이 하락 진행 아님' 매매 신호를 잠정 계산해 live.json에 쓴다.
바닥 판정(6개 항목)은 장중에 다시 계산하지 않고 전 거래일 종가 기준 값을 그대로 쓴다.

종료 코드: 0 = live.json 작성, 3 = 장중이 아니거나 오늘 데이터 없음(배포할 것 없음)
참고용이며 투자 자문이 아니다.
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from kospi_bottom_model import OUT, naver_kospi

EMA_DAYS = 60


def main() -> int:
    now = pd.Timestamp.now(tz="Asia/Seoul")
    if now.weekday() >= 5 or not ((9, 0) <= (now.hour, now.minute) < (15, 40)):
        print("장중이 아님:", now)
        return 3

    sig = pd.read_csv(OUT / "signals_daily.csv", parse_dates=["date"]).set_index("date")
    n = naver_kospi()
    today = pd.Timestamp(now.date())
    if n.index[-1] != today:
        print("오늘 시세 없음(휴장일일 수 있음). 마지막:", n.index[-1].date())
        return 3

    closes = sig["kospi"].dropna()
    closes = closes[closes.index < today]
    price = float(n.iloc[-1])
    prev = float(closes.iloc[-1])
    series = pd.concat([closes, pd.Series([price], index=[today])])
    ema = float(series.ewm(span=EMA_DAYS, adjust=False, min_periods=EMA_DAYS).mean().iloc[-1])

    state = str(sig["state"].dropna().iloc[-1])
    hold = bool(price > ema and state != "하락 진행")
    out = {
        "time_kst": now.strftime("%Y-%m-%d %H:%M"),
        "kospi": round(price, 2),
        "prev_close": round(prev, 2),
        "prev_date": f"{closes.index[-1]:%Y-%m-%d}",
        "change_pct": round((price / prev - 1) * 100, 2),
        "ema_days": EMA_DAYS,
        "ema": round(ema, 2),
        "state": state,
        "state_date": f"{sig['state'].dropna().index[-1]:%Y-%m-%d}",
        "signal": "보유" if hold else "현금",
        "provisional": True,
    }
    (OUT / "live.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
