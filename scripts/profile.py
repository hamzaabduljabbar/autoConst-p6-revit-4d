"""Step 3: brief.md - both sides summarised, so the mapping is written from the whole picture.

    python profile.py --job outputs/<job>
"""
import argparse, collections, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import read_csv


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--job", required=True); a = ap.parse_args()
    S = read_csv(os.path.join(a.job, "schedule.csv"))
    E = read_csv(os.path.join(a.job, "elements.csv"))
    L = ["# Brief: schedule and model", ""]

    # schedule
    L += ["## Schedule", f"{len(S)} activities. Types: " +
          ", ".join(f"{k} {v}" for k, v in collections.Counter(r['type'] for r in S).most_common()), ""]
    names = collections.Counter(r["name"].lower() for r in S)
    rep = [n for n, c in names.items() if c > 1]
    L.append(f"Names that repeat (location must come from WBS/codes/dates): {len(rep)} of {len(names)}")
    L.append("")
    by_wbs = collections.OrderedDict()
    for r in sorted(S, key=lambda r: (r["wbs"], r["start"])):
        by_wbs.setdefault(r["wbs"], []).append(r)
    for w, rs in by_wbs.items():
        L.append(f"**{w or '(no WBS)'}** ({len(rs)})")
        for r in rs:
            L.append(f"- {r['activity_id']} | {r['name']} | {r['start']} > {r['finish']} | {r['dur_days']} d | {r['type']}"
                     + (f" | {r['codes']}" if r["codes"] else ""))
        L.append("")

    # model
    lv = collections.defaultdict(list)
    for e in E:
        if e.get("zmin"): lv[e["level"]].append(int(e["zmin"]))
    L += ["## Model", f"{len(E)} elements.", "", "Levels (median element base height, mm):"]
    for k, v in sorted(lv.items(), key=lambda kv: sorted(kv[1])[len(kv[1]) // 2]):
        L.append(f"- {k or '(no level)'}: {len(v)} elements, median z {sorted(v)[len(v)//2]}")
    L += ["", "Groups (level | category | family : type | function | structural | material): count", ""]
    g = collections.Counter((e["level"] or "-", e["category"], f"{e['family']} : {e['type']}", e["function"], e["structural"], e["material"]) for e in E)
    for (lvl, cat, ft, fn, st, mat), c in sorted(g.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1])):
        L.append(f"- {lvl} | {cat} | {ft[:60]} | {fn} | {st} | {mat}: {c}")
    xs = [int(e["cx"]) for e in E if e.get("cx")]
    if xs:
        L += ["", f"Plan extent x {min(xs)}..{max(xs)} mm, y {min(int(e['cy']) for e in E if e.get('cy'))}.."
                  f"{max(int(e['cy']) for e in E if e.get('cy'))} mm (use cx/cy to split buildings/zones)"]
    open(os.path.join(a.job, "brief.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"brief.md: {len(S)} activities, {len(by_wbs)} WBS groups, {len(E)} elements, {len(g)} element groups")


if __name__ == "__main__":
    main()
