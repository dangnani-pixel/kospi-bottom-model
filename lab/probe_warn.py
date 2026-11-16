import re, urllib.request, urllib.parse
from pathlib import Path
out = []
def get(url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
links = set()
for url in ["https://kind.krx.co.kr/main.do?method=loadInitPage&scrnmode=1", "https://kind.krx.co.kr/main.do", "https://kind.krx.co.kr/common/js/kind_menu.js", "https://kind.krx.co.kr/js/menu.js"]:
    try:
        h = get(url); links |= set(re.findall(r"(/?investwarn/\w+\.do[^\"' ]*)", h)); out.append(f"[OK] {url} len={len(h)}")
        for m in re.findall(r"[^\n]{0,80}투자주의[^\n]{0,120}", h)[:6]: out.append("  ctx: " + m.strip()[:200])
    except Exception as e: out.append(f"[FAIL] {url} {e}")
out.append("investwarn links: " + str(sorted(links)[:40]))
for l in sorted(links):
    if "attent" in l.lower() or "caution" in l.lower():
        try:
            h = get("https://kind.krx.co.kr" + (l if l.startswith("/") else "/" + l)); out.append(f"[GET {l}] len={len(h)} methods={sorted(set(re.findall(r'method[^a-zA-Z]{1,6}(\\w+)', h)))[:20]}")
        except Exception as e: out.append(f"[GET {l}] {e}")
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/warn_probe2.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
