"""관세청 수출입총괄 API 탐색: data.go.kr 상세 페이지에서 요청주소를 찾고, 키로 실제 호출해 응답을 저장(키는 가림)."""
import os, re, json, urllib.request, urllib.parse, pathlib
OUT = pathlib.Path("lab/out"); OUT.mkdir(parents=True, exist_ok=True)
KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
log = [f"key set: {bool(KEY)} len={len(KEY)}"]
UA = {"User-Agent": "Mozilla/5.0"}
def get(url, n=200000):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.status, r.read(n).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(3000).decode("utf-8", "replace")
    except Exception as e:
        return None, repr(e)
def redact(s): return s.replace(KEY, "<KEY>").replace(urllib.parse.quote(KEY, safe=""), "<KEY>") if KEY else s
endpoints = set()
for pid in ["15101607", "15134343", "15101641", "15101609", "15101630", "15100475", "15102108", "15101612", "15101608"]:
    for url in [f"https://www.data.go.kr/data/{pid}/openapi.do", f"https://www.data.go.kr/catalog/{pid}/openapi.json"]:
        st, body = get(url)
        title = re.search(r"<title>(.*?)</title>", body or "", re.S)
        eps = set(re.findall(r"https?://apis\.data\.go\.kr/1220000/[A-Za-z0-9_/]+", body or ""))
        names = set(re.findall(r"관세청_[^<\"'\n]{2,30}", body or ""))
        log.append(f"{url} -> {st} title={title.group(1).strip()[:80] if title else None} names={sorted(names)[:5]} eps={sorted(eps)}")
        endpoints |= eps
        if url.endswith(".json") and st == 200:
            (OUT / f"customs_{pid}.json").write_text(body[:60000])
log.append("ENDPOINTS: " + json.dumps(sorted(endpoints)))
for ep in sorted(endpoints):
    for params in [{"strtYymm": "202501", "endYymm": "202512"}, {"strtYymm": "202501", "endYymm": "202512", "cntyCd": "US"}]:
        q = urllib.parse.urlencode({"serviceKey": KEY, **params})
        st, body = get(f"{ep}?{q}", 6000)
        log.append(f"CALL {ep} {params} -> {st}\n{redact(body)[:2500]}\n")
(OUT / "customs_probe.txt").write_text(redact("\n".join(log)))
print(redact("\n".join(log))[:4000])
