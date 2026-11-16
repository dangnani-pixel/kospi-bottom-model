import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import http_get
out = []
h = http_get("https://finance.naver.com/sise/investment_alert.naver", tries=1).decode("utf-8", "ignore")
apis = sorted(set(re.findall(r'https?://[\w.\-]+/[\w/\-.]*api[\w/\-.{}?=&]*', h)))[:40]
out.append("html apis: " + str(apis))
chunks = sorted(set(re.findall(r'(/[\w/\-.]*_next/static/chunks/[\w/\-.]+\.js)', h)))
out.append(f"chunks {len(chunks)}")
found = set()
for c in chunks:
    url = c if c.startswith("http") else "https://ssl.pstatic.net" + c if "imgstock" in c else "https://finance.naver.com" + c
    try:
        js = http_get(url, tries=1).decode("utf-8", "ignore")
    except Exception:
        try: js = http_get("https://ssl.pstatic.net/imgstock/fn/real/pc" + c[c.find("/_next"):], tries=1).decode("utf-8", "ignore")
        except Exception as e: continue
    for m in re.findall(r'["\'`]([^"\'`]{0,80}(?:alert|caution|warning|Alert|Caution|Warning|investment)[^"\'`]{0,80})["\'`]', js):
        if "/" in m: found.add(m)
out.append("js strings: " + str(sorted(found)[:60]))
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/warn_probe4.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
