"""S&P Global 보도자료 목록 구조 확인."""
import re, urllib.request, pathlib
OUT = pathlib.Path("lab/out"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40) as r: return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e: return e.code, e.read(3000).decode("utf-8", "replace")
    except Exception as e: return None, repr(e)
log = []
for u in ["https://www.pmi.spglobal.com/Public/Release/PressReleases",
          "https://www.pmi.spglobal.com/Public/Release/PressReleases?language=en",
          "https://www.pmi.spglobal.com/Public/Home/PressRelease/15885ffcd983479d9760a833ace5a4e0",
          "https://www.pmi.spglobal.com/Public/Home/PressRelease/d24db6b6b62745c1970931ac3b4323c5"]:
    st, b = get(u)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b))
    links = sorted(set(re.findall(r'href="([^"]*PressRelease[^"]*)"', b)))[:30]
    ajax = sorted(set(re.findall(r'["\'](/Public/[^"\']+)["\']', b)))[:40]
    log.append(f"== {u} -> {st} len={len(b)}\nlinks={links}\nPublic paths={ajax}\nTEXT: {t[:1500]}\n")
    m = re.search(r"Korea.{0,300}", t)
    if m: log.append("KOREA CTX: " + m.group(0))
    for kw in ["PMI", "posted", "registered", "Headline"]:
        i = t.find(kw)
        if i >= 0: log.append(f"[{kw}] {t[max(0,i-200):i+500]}")
(OUT / "pmi_probe.txt").write_text("\n".join(log))
