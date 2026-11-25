"""수출입총괄 getNewtradeList를 키 형태(그대로/디코딩)별로 호출. 키 값은 출력하지 않음."""
import os, urllib.request, urllib.parse, pathlib
OUT = pathlib.Path("lab/out"); OUT.mkdir(parents=True, exist_ok=True)
RAW = os.environ.get("DATA_GO_KR_KEY", "").strip()
log = [f"len={len(RAW)} has_percent={'%' in RAW} ends_eq={RAW.endswith('=')} has_plus={'+' in RAW} has_slash={'/' in RAW} has_space={' ' in RAW}"]
def call(key_in_url):
    url = f"https://apis.data.go.kr/1220000/Newtrade/getNewtradeList?serviceKey={key_in_url}&strtYymm=202501&endYymm=202512"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            return r.status, r.read(6000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2000).decode("utf-8", "replace")
dec = urllib.parse.unquote(RAW)
variants = {"raw_as_is": RAW, "quote(decoded)": urllib.parse.quote(dec, safe=""), "quote(raw)": urllib.parse.quote(RAW, safe="")}
for name, k in variants.items():
    st, body = call(k)
    for s in {RAW, dec, k, urllib.parse.quote(dec, safe="")}: body = body.replace(s, "<KEY>")
    log.append(f"== {name} -> {st}\n{body[:3000]}")
(OUT / "customs_probe3.txt").write_text("\n".join(log))
