"""관세청 수출입총괄(GW) 세부 오퍼레이션·항목 확인 (키는 가림)."""
import os, re, json, html, urllib.request, urllib.parse, pathlib
OUT = pathlib.Path("lab/out"); OUT.mkdir(parents=True, exist_ok=True)
KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
UA = {"User-Agent": "Mozilla/5.0"}
def get(url, n=400000):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.status, r.read(n).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(4000).decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)
def redact(s): return s.replace(KEY, "<KEY>").replace(urllib.parse.quote(KEY, safe=""), "<KEY>") if KEY else s
log = []
st, page = get("https://www.data.go.kr/data/15102108/openapi.do")
log.append(f"page {st} len={len(page)}")
ops = sorted(set(re.findall(r"(?:Newtrade/)?(get[A-Za-z0-9]+)", page)))
log.append("get* tokens: " + json.dumps(ops))
log.append("Newtrade paths: " + json.dumps(sorted(set(re.findall(r"Newtrade/[A-Za-z0-9_]+", page)))))
swag = sorted(set(re.findall(r"[\"'](/[^\"']*swagger[^\"']*|[^\"']*oas[^\"']*\.json)[\"']", page)))
log.append("swagger refs: " + json.dumps(swag[:10]))
# 페이지에서 요청/응답 항목 표 주변 텍스트
txt = re.sub(r"<[^>]+>", " ", page); txt = html.unescape(re.sub(r"\s+", " ", txt))
for kw in ["요청변수", "출력결과", "strtYymm", "expDlr", "기간", "hsSgn"]:
    i = txt.find(kw)
    if i >= 0: log.append(f"[{kw}] ..." + txt[max(0, i-200):i+1500])
cands = set(o for o in ops if "trade" in o.lower() or "Newtrade" in o) | {"getNewtradeList", "getNewtradeSmmryList", "getNewtrade"}
for op in sorted(cands):
    for params in [{"strtYymm": "202501", "endYymm": "202512"}]:
        q = urllib.parse.urlencode({"serviceKey": KEY, **params})
        st, body = get(f"https://apis.data.go.kr/1220000/Newtrade/{op}?{q}", 20000)
        log.append(f"CALL {op} {params} -> {st}\n{redact(body)[:4000]}\n")
(OUT / "customs_probe2.txt").write_text(redact("\n".join(log)))
