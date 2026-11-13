"""KRX 과거 이력 수집 (GitHub Actions에서 실행, KRX_ID/KRX_PW 필요).

- data/breadth_history.csv   : 날짜별 코스피 상승/하락/보합 종목 수 (하루 1회 호출이라 처음엔 오래 걸림)
- data/investor_history.csv  : 날짜별 코스피 투자자별 순매수 대금(원)
- data/fundamental_history.csv: 코스피 지수 PER/PBR/배당수익률 (KRX 공식, 후행 기준)
이미 있는 날짜는 건너뛰므로 끊겨도 다시 돌리면 이어서 받는다.
"""
import sys, time
from pathlib import Path
import pandas as pd
from pykrx import stock

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)
START = "2002-01-01"
BUDGET = float(sys.argv[1]) * 60 if len(sys.argv) > 1 else 260 * 60
t0 = time.time()
today = pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None).normalize()

def yearly(fn, start, end):
    frames, a = [], pd.Timestamp(start)
    while a <= end:
        b = min(a + pd.Timedelta(days=364), end)
        df = fn(a.strftime("%Y%m%d"), b.strftime("%Y%m%d"))
        if df is not None and len(df):
            frames.append(df)
        a = b + pd.Timedelta(days=1); time.sleep(0.3)
    return pd.concat(frames) if frames else pd.DataFrame()

def merge_save(path, new, key="date"):
    if path.exists():
        old = pd.read_csv(path, dtype={key: str})
        new = pd.concat([old[~old[key].isin(new[key])], new], ignore_index=True)
    new.sort_values(key).to_csv(path, index=False)
    return new

# 1) 투자자별 순매수
p = DATA / "investor_history.csv"
start = START
if p.exists():
    start = (pd.to_datetime(pd.read_csv(p)["date"]).max() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
inv = yearly(lambda a, b: stock.get_market_trading_value_by_date(a, b, "KOSPI"), start, today)
if len(inv):
    inv.index = pd.to_datetime(inv.index)
    out = pd.DataFrame({"date": inv.index.strftime("%Y-%m-%d"), "foreign": inv["외국인합계"].values,
                        "institution": inv["기관합계"].values, "individual": inv["개인"].values})
    out = merge_save(p, out); print("investor", len(out), out["date"].min(), out["date"].max())

# 2) 지수 PER/PBR/배당
p = DATA / "fundamental_history.csv"
start = START
if p.exists():
    start = (pd.to_datetime(pd.read_csv(p)["date"]).max() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
f = yearly(lambda a, b: stock.get_index_fundamental(a, b, "1001"), start, today)
if len(f):
    f.index = pd.to_datetime(f.index)
    out = pd.DataFrame({"date": f.index.strftime("%Y-%m-%d"), "per": f["PER"].values, "pbr": f["PBR"].values,
                        "div_yield": f["배당수익률"].values})
    out = merge_save(p, out); print("fundamental", len(out), out["date"].min(), out["date"].max())

# 3) 시장 폭 (날짜별 1회 호출)
p = DATA / "breadth_history.csv"
days = yearly(lambda a, b: stock.get_index_ohlcv(a, b, "1001"), START, today).index
days = pd.to_datetime(days).strftime("%Y-%m-%d")
have = set(pd.read_csv(p, dtype={"date": str})["date"]) if p.exists() else set()
todo = [d for d in days if d not in have]
print("breadth todo", len(todo))
rows = []
for k, d in enumerate(todo):
    if time.time() - t0 > BUDGET:
        print("time budget reached"); break
    try:
        df = stock.get_market_ohlcv_by_ticker(d.replace("-", ""), market="KOSPI")
        ch = df["등락률"]
        rows.append({"date": d, "up": int((ch > 0).sum()), "down": int((ch < 0).sum()), "flat": int((ch == 0).sum())})
    except Exception as e:
        print("fail", d, e); time.sleep(2)
    if len(rows) >= 200:
        merge_save(p, pd.DataFrame(rows)); rows = []; print("saved through", d, f"{k+1}/{len(todo)}", flush=True)
    time.sleep(0.15)
if rows:
    merge_save(p, pd.DataFrame(rows))
print("breadth total", len(pd.read_csv(p)) if p.exists() else 0)
