import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import new_highs as n
uni = n.universe(); admin = n.admin_issues()
names = {(u["market"], u["name"].replace(" ", "")) for u in uni}
matched = admin & names; unmatched = sorted(admin - names)
flag_halt = sum(1 for u in uni if (u["market"], u["name"].replace(" ", "")) in admin and u["stop_flag"])
out = f"admin {len(admin)} matched {len(matched)} (of which halted {flag_halt}) unmatched {len(unmatched)}: {unmatched[:40]}"
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/admin_match.txt").write_text(out, encoding="utf-8"); print(out)
