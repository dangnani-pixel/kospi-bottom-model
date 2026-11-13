"""데이터 소스 확인용 (GitHub Actions에서 실행). 결과는 lab/out/probe.txt."""
import json, sys, time, traceback
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import fred, yahoo, http_get

OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
log = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s); log.append(s)

def tryit(name, fn):
    try:
        r = fn()
        if isinstance(r, (pd.Series, pd.DataFrame)):
            p(f"[OK] {name}: {len(r)} rows, {r.index[0] if len(r) else ''} ~ {r.index[-1] if len(r) else ''}")
            p("     tail:", r.tail(2).to_string().replace("\n", " | ")[:300])
        else:
            p(f"[OK] {name}: {str(r)[:300]}")
    except Exception as e:
        p(f"[FAIL] {name}: {type(e).__name__}: {str(e)[:200]}")

# FRED macro
for sid in ["DTWEXBGS", "XTEXVA01KRM667S", "XTEXVA01KRM664S", "KORCPIALLMINMEI", "CPALTT01KRM659N",
            "IRSTCB01KRM156N", "IRSTCI01KRM156N", "INTDSRKRM193N", "IR3TIB01KRM156N", "DGS10", "BAMLH0A0HYM2", "VIXCLS"]:
    tryit("FRED " + sid, lambda sid=sid: fred(sid))
for t in ["^VKOSPI", "^KS200", "KRW=X"]:
    tryit("Yahoo " + t, lambda t=t: yahoo(t))

from pykrx import stock
tryit("pykrx index list KOSPI", lambda: [(t, stock.get_index_ticker_name(t)) for t in stock.get_index_ticker_list(market="KOSPI")][:60])
for m in ["KRX", "테마"]:
    tryit(f"pykrx index list {m} 변동성", lambda m=m: [(t, stock.get_index_ticker_name(t)) for t in stock.get_index_ticker_list(market=m) if "변동성" in stock.get_index_ticker_name(t)])
for code in ["1300", "1311", "5300", "5301", "1028"]:
    tryit(f"pykrx index ohlcv {code}", lambda code=code: stock.get_index_ohlcv("20200301", "20200331", code))
tryit("pykrx investor value KOSPI 2008", lambda: stock.get_market_trading_value_by_date("20081001", "20081031", "KOSPI"))
tryit("pykrx investor value KOSPI 2002", lambda: stock.get_market_trading_value_by_date("20020401", "20020430", "KOSPI"))
def breadth():
    t0 = time.time(); df = stock.get_market_ohlcv_by_ticker("20200319", market="KOSPI")
    return f"cols={list(df.columns)} n={len(df)} up={(df['등락률']>0).sum()} down={(df['등락률']<0).sum()} sec={time.time()-t0:.1f}"
tryit("pykrx breadth 2020-03-19", breadth)
def breadth02():
    df = stock.get_market_ohlcv_by_ticker("20020603", market="KOSPI"); return f"n={len(df)} up={(df['등락률']>0).sum()}"
tryit("pykrx breadth 2002-06-03", breadth02)
tryit("pykrx index fundamental (PER) 2020", lambda: stock.get_index_fundamental("20200301", "20200310", "1001"))
(OUT / "probe.txt").write_text("\n".join(log), encoding="utf-8")
