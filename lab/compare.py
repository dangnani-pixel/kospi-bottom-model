import sys, numpy as np, pandas as pd
sys.path.insert(0, "lab/new"); import kospi_bottom_model as K
out = []
def load(p):
    d = pd.read_csv(p, parse_dates=["date"]).set_index("date"); d["high_252"] = d.kospi.rolling(252, min_periods=60).max()
    d["_on"] = d.state.isin(["바닥 확인 중", "회복"]).astype(int); return d
D = {"기존": load("lab/old/signals_daily.csv"), "수정": load("lab/new/signals_daily.csv")}
for name, d in D.items():
    eps = [e for e in K.episodes(d) if e["end"] is not None]; sc = [K.score(d, e, "_on") for e in eps]
    px = d.kospi; ret = px.pct_change().fillna(0); ema = px.ewm(span=60, adjust=False, min_periods=60).mean()
    line = [f"== {name}: 헛신호 {sum(s['false_n'] for s in sc)}, 지연 {[s['lag'] for s in sc]}, 추가하락 최악 {[None if s['worst_fall'] is None else round(s['worst_fall']*100,1) for s in sc]}"]
    for rn, pos in [("EMA60+판정", (px > ema) & (d.state != "하락 진행")), ("판정 on만", d._on == 1), ("판정만(≠하락진행)", d.state != "하락 진행")]:
        for a in ["2016-11-14", "2003-01-01"]:
            h = pos.astype(float).shift(1).fillna(0); r = (h*ret - h.diff().abs().fillna(0)*0.00015).loc[a:]; eq = (1+r).cumprod()
            line.append(f"   {rn} {a[:4]}~: {(eq.iloc[-1]**(252/len(r))-1)*100:.1f}% / MDD {(eq/eq.cummax()-1).min()*100:.1f}% / SR {r.mean()/r.std()*np.sqrt(252):.2f}")
    last = d.iloc[-1]
    line.append(f"   마지막 {d.index[-1].date()} 판정 {last.state} ({last.conditions_met}) " + " ".join(f"{c}={last[c]}" for c in K.COND_COLS))
    line.append(f"   자료 없음 비율: " + " ".join(f"{c} {d[c].isna().mean():.3f}" for c in K.COND_COLS))
    out += line
a, b = D["기존"].state.align(D["수정"].state, join="inner")
out.append(f"판정이 다른 날 비율 {(a != b).mean():.1%} ({(a != b).sum()}일 / {len(a)}일)")
out.append(pd.crosstab(a, b).to_string())
open("lab/out/compare.txt", "w").write("\n".join(out)); print("\n".join(out))
